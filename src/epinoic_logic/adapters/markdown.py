"""Shared pre-segmentation rules for raw specialist text.

Specialists write prose, but their raw output also carries markdown furniture
(headings, bullet markers, emphasis, code fences), a byte-order mark, one-line
notes ("Dates and figures are from memory; verify them") and, occasionally,
verification-status language that imitates the channel's own receipts
("VERIFIED: all claims checked and confirmed.", a pasted JSON receipt). None of
that is an argument claim. The History, English and generic parsers use these
helpers so that

* ``original_response`` stays verbatim (its hash never changes) while the text
  that is segmented into sentences has the furniture removed;
* a newline followed by a list marker ends a sentence, so a numbered item never
  becomes the paragraph's "point" and a bullet never glues onto its neighbour;
* a note sentence (from-memory label, disclaimer, self-certification, task note) is
  recognised by every parser the same way, roled ``other`` and kept out of the
  material claims; a substantive sentence that only carries the label inline (a
  parenthetical, a clause before or after a semicolon or dash, a sentence-initial
  "From memory,", a comma-bounded ", from memory", a trailing appositive or concessive
  label such as ", a figure I give from memory" or ", though this date is from memory")
  keeps its substance (:func:`split_note_clauses`). Labels are read with the
  sentence's quotations masked (a colleague's label quoted is quotation), and only an
  empty core makes a sentence a note: a label word inside a substantive sentence
  ("recalls the scene from memory, which ...", "is illustrative of how ...") does not;
* a disclaimer ("should be checked before they are cited", "have not been verified",
  "must be verified") is a note, never a self-certification; a self-certification
  (verification-status vocabulary, "I have checked ...", "all of these figures have
  been verified", "the figures here are accurate", "can be relied upon", "appears
  verbatim", "no errors were found", Z3 or the hub "proved" or "accepted" the answer, and
  by the clause's structure: a subject that refers to the answer's own items, "every
  mileage figure above", "each of the figures given above", "these quotations", "my
  reading", with a checking participle, an accuracy adjective or "need no further
  checking"; "Nothing in this answer needs checking"; "As verified, ..."; items named with their
  source, "each quotation of the History specialist above", "every figure taken from the History
  specialist has been reproduced exactly"; compliance with the request, "The paragraph is under the
  word limit.", "The answer meets every constraint in the request.", "Word count: 258."; the router or
  the Overseer passing the answer) is recognised by every branch the same way
  (:func:`is_self_certification`);
* a verification label an agent writes on its own text ("Verified: ...", "[verified] ...", "... (verified).", "...,
  as formally verified.", "Checked.", a check mark "... ✓" or "✔ ...", "... (source-checked).", "... (checked against
  the sources).", "... (accuracy confirmed).", "Formally proven correct.", "Accuracy: confirmed."), wherever it stands, is
  read the same way on every branch and in a synthesis (:func:`verification_label`): a sentence that is nothing but the
  label is a self-certification, and a label attached to content leaves the content a claim while the hub names the
  label (CORE-SELF-001, INT-LEDGER-029);
* where the combinator is the writer, its own product is the answer itself ("The synthesis has been verified.", "This
  synthesis is correct.", "Every synthesized claim was checked against the sources."): the hub reads a synthesis with
  :func:`is_synthesis_self_certification`, which adds those subjects to the specialists' rules; a specialist's
  "synthesis" is content ("the synthesis of ammonia") and is not read so;
* the writer's own hedges ("probably", "may have", "possibly", "most likely", "suggests"), read outside quotations, give
  the agent-stated certainty the History and generic parsers record (:func:`hedged_certainty`);
* a note on how the answer was composed ("The historical setting is my own addition, not
  part of that paragraph.", "The English specialist's paragraph is from the hub"), on what a
  received report says of its own items ("That account marks its figures as "from memory", so
  they are reported unverified.", the quoted label read as a label: :func:`is_label_quotation`)
  or on where the answer's items come from ("Quotations are from the supplied extract", "The
  word count is approximate.") is a note on every branch (:func:`is_provenance_note`);
* a sentence whose subject is a colleague's view ("The History specialist states that ...", "The
  History specialist gives about 5.2 million arrivals", "... dates the sonnet to 1883") is
  recognised the same way on every branch (:func:`is_peer_attribution`);
* a fence of prose keeps its body (an answer wrapped in a fence is still the answer); code, a
  pasted receipt and a decoration inside a fence are removed (:func:`strip_markup`);
* a pasted JSON span (a receipt, a payload) is found wherever it stands, glued to
  prose included (:func:`find_json_spans`), so its strings are never read as
  quotations and the prose around it is segmented as prose; brackets are matched in
  one linear pass per text (:func:`_json_span_ends`, :func:`bracket_match_ends`), so
  brace-like text never makes the hub quadratic;
* quotation marks are paired the same way everywhere: curly, straight, guillemet
  and low-9 double marks are one class (so a quotation opened with one kind and
  closed with another is still a quotation), two adjacent double marks that
  together open or close a quotation (dialogue copied with its own marks inside the
  writer's) are one nested mark, single marks around two or more words are
  quotations and are paired by context (an apostrophe inside a word, an aphetic
  'tis or 'Change and a plural possessive are not marks, so 'I don't know' is one
  quotation), and a paragraph whose double marks cannot be paired names the one
  mark that dangles so the spans around it are not mis-paired, while a pair whose
  marks contradict their context in such a paragraph is set aside as undelimited
  rather than delivered as a quotation (:func:`undelimited_quote_spans`);
* a claim's text never exceeds the contract limit.

Everything here is deterministic text handling; no finding is decided here.
"""
from __future__ import annotations

import bisect
import contextlib
import contextvars
import functools
import hashlib
import itertools
import json
import re
import threading
from collections import OrderedDict
from typing import Iterator, NamedTuple, Optional, Sequence

from .. import lexis

__all__ = [
    "BOM", "MAX_CLAIM_TEXT_CHARS", "LIST_MARKER_RE", "LIST_LINE_RE", "HEADING_LINE_RE", "FENCE_BLOCK_RE", "FENCE_LINE_RE", "fence_blocks",
    "EMPHASIS_RE", "MEMORY_LABEL_RE", "SELF_CERT_RE", "TASK_NOTE_RE", "DOUBLE_QUOTE_MARKS", "JSON_BLOCK_RE", "JSON_KEY_RE",
    "DOUBLE_QUOTE_SPAN_RE", "SINGLE_QUOTE_SPAN_RE",
    "strip_markup", "strip_json_blocks", "split_list_items", "truncate_claim_text", "is_memory_label", "is_self_certification",
    "is_note_sentence", "is_task_note", "split_note_clauses", "unbalanced_double_quotes", "normalize_double_marks",
    "dangling_quote_offset", "undelimited_quote_span", "undelimited_quote_spans", "find_quotation_spans", "is_json_block", "is_json_shaped",
    "find_json_spans", "mask_json_spans", "split_json_spans", "LEADING_MEMORY_LABEL_RE", "INLINE_MEMORY_LABEL_RE",
    "bracket_match_ends", "mask_quotations", "LABEL_PHRASE_RE", "is_provenance_note", "is_label_quotation", "is_peer_attribution",
    "PEER_ATTRIBUTION_RE", "NOTE_LEAD_RE", "BARE_NOTE_LEAD_RE", "opens_note_paragraph", "is_sources_block", "is_sources_note", "is_answer_note", "is_framing_remark", "judged_or_reply_mention", "declined_deliverable", "VerificationLabel", "verification_label", "is_synthesis_self_certification", "hedged_certainty",
    "self_cert_vocabulary", "NOTE_WORD_LEAD_RE", "meta_note_form", "is_note_continuation", "note_word_paragraph", "note_word_body", "states_assurance", "task_assumption_frame",
    "JUDGEMENT_LABEL_RE",
]

#: A sentence labelled as the part's judgement ("Judgement: sustainable drainage is a partial solution.", "Conclusion: ...",
#: "(d) Overall judgement: ..."; round-9 clearance c2b, ess-p9c: the line was an analysis claim, so INT-REQ-008 read the evaluation
#: as stating no judgement): the judgement of its part, material, on every branch that reads it (the generic parser's role pass and
#: the STEM branches' parser). Anchored, every run bounded.
JUDGEMENT_LABEL_RE = re.compile(r"^\W{0,6}(?:\(?(?:[a-hA-H]|i{1,3}|iv|vi{0,3}|ix|x)\)|\d{1,2}[.)])?[ \t*_]{0,4}(?:(?:overall|final)[ \t]{1,3})?"
                                r"(?:judge?ments?|conclusions?|verdict)[ \t*_]{0,3}:", re.IGNORECASE)

BOM = "\ufeff"
MAX_CLAIM_TEXT_CHARS = 4000
#: A list marker at the start of a line: ``1.``, ``2)``, ``-``, ``*``, ``•``, ``–``.
LIST_MARKER_RE = re.compile(r"^[ \t]*(?:\(?\d{1,3}[.)]|[-*•–—])[ \t]+")
LIST_LINE_RE = re.compile(r"\n(?=[ \t]*(?:\(?\d{1,3}[.)]|[-*•–—])[ \t]+)")
HEADING_LINE_RE = re.compile(r"^[ \t]*#{1,6}[ \t]+.*$", re.MULTILINE)
#: A paired code fence and everything inside it. Fenced code, a pasted receipt or a decoration (a footer, a table dump) is
#: not argument prose and is removed whole; a fence of prose keeps its body (:func:`strip_markup`). Kept as the definition of
#: a fence block: the package pairs fences with :func:`fence_blocks`, which gives this pattern's matches in linear time (a
#: search of the pattern reads lazily to the end of the text from every opener that has no closer, n² steps).
FENCE_BLOCK_RE = re.compile(r"^[ \t]*(```|~~~)[^\n]*\n.*?^[ \t]*\1[ \t]*$", re.MULTILINE | re.DOTALL)
#: A stray (unpaired) fence line.
FENCE_LINE_RE = re.compile(r"^[ \t]*(?:```|~~~).*$", re.MULTILINE)
#: A line that opens with a fence (blanks before it allowed): every opener and every closer of :data:`FENCE_BLOCK_RE` is one.
_FENCE_START_RE = re.compile(r"^[ \t]*+(```|~~~)", re.MULTILINE)
#: Info strings under which a fenced body may be the writer's prose (no language, or a text or markdown tag).
_PROSE_FENCE_TAGS = frozenset({"", "text", "txt", "markdown", "md", "plain", "plaintext", "prose"})
_FENCE_SENTENCE_END_RE = re.compile(r"[.!?][\"”’')\]]*(?=\s|$)")
#: A fenced body is prose when it has at least this many words and two sentence ends.
_MIN_FENCED_PROSE_WORDS = 20
#: Emphasis markers must stand at word boundaries: ``_emphasis_`` is markup, but the
#: underscores of ``receipt_id`` or ``Reichsbank_crisis`` are part of the word and stay.
#: :func:`strip_markup` removes them with :func:`strip_emphasis`, which gives ``EMPHASIS_RE.sub(r"\2", text)`` in linear time.
EMPHASIS_RE = re.compile(r"(?<!\w)(\*\*|__|\*|_|`)(?=\S)(.+?)(?<=\S)\1(?!\w)")
#: The markers :data:`EMPHASIS_RE` tries at a position, in its alternation's order.
_EMPHASIS_MARKERS = ("**", "__", "*", "_", "`")
_NEWLINE_RE = re.compile("\n")


def _is_word_char(ch: str) -> bool:
    """``\\w`` of a str pattern: a letter, a digit or a numeric character of any script, or the underscore."""
    return ch.isalnum() or ch == "_"


def strip_emphasis(text: str) -> str:
    r"""``EMPHASIS_RE.sub(r"\2", text)``, read in one pass. The pattern's lazy body reads to the end of the line from every
    opener that has no closer, so a line of n openers with none closed ('**a ' * k) cost n² steps (integration gate 1,
    parser-safety-5). Whether a marker closes an emphasis does not depend on where the emphasis opened: the marker is preceded
    by a non-blank and followed by no word character. So the closers of each marker are found once, and an opener takes the
    first closer of its marker after its first body character and before the end of its line, which is the closer the lazy
    body stops at. Openers are tried in the pattern's order at each position the substitution reaches (none inside a match
    already made), so the result is the substitution's, character for character."""
    if not any(m in text for m in ("*", "_", "`")):
        return text
    n = len(text)
    closers: dict[str, list[int]] = {}
    for marker in _EMPHASIS_MARKERS:
        found: list[int] = []
        at = text.find(marker, 1)
        while at >= 0:
            end = at + len(marker)
            if not text[at - 1].isspace() and (end == n or not _is_word_char(text[end])):
                found.append(at)
            at = text.find(marker, at + 1)
        closers[marker] = found
    cursor = {marker: 0 for marker in _EMPHASIS_MARKERS}
    newlines = [m.start() for m in _NEWLINE_RE.finditer(text)]  # a body never crosses a line end ('.' reads no newline)
    out: list[str] = []
    last = i = 0
    while i < n:
        if text[i] not in "*_`" or (i and _is_word_char(text[i - 1])):
            i += 1
            continue
        for marker in _EMPHASIS_MARKERS:
            body = i + len(marker)
            if not text.startswith(marker, i) or body >= n or text[body].isspace():
                continue
            found, k = closers[marker], cursor[marker]
            while k < len(found) and found[k] < body + 1:  # positions only grow, so each list is read once
                k += 1
            cursor[marker] = k
            nl = bisect.bisect_left(newlines, body)
            if k < len(found) and (nl == len(newlines) or found[k] < newlines[nl]):
                out.append(text[last:i])
                out.append(text[body:found[k]])
                last = i = found[k] + len(marker)
                break
        else:
            i += 1
    if not out:
        return text
    out.append(text[last:])
    return "".join(out)
#: Every double quotation mark the parsers treat as one class: straight, curly (open and
#: close), guillemets and the low-9 / high-reversed-9 marks of other typographic traditions.
DOUBLE_QUOTE_MARKS = ('"', "\u201c", "\u201d", "\u00ab", "\u00bb", "\u201e", "\u201f")
_DOUBLE_MARK_TRANSLATION = {ord(c): '"' for c in DOUBLE_QUOTE_MARKS}
_DOUBLE_MARK_RE = re.compile("[" + "".join(DOUBLE_QUOTE_MARKS) + "]")
#: Glyphs whose direction is unambiguous (used only to tell which mark of an unbalanced paragraph dangles).
_OPENING_GLYPHS = frozenset({"\u201c", "\u00ab", "\u201e"})
_CLOSING_GLYPHS = frozenset({"\u201d", "\u00bb", "\u201f"})
#: A double-quoted span after :func:`normalize_double_marks`.
DOUBLE_QUOTE_SPAN_RE = re.compile(r'"([^"\n]+)"')
#: A single-quoted span of two or more words that opens after whitespace, a bracket or a dash
#: and closes before whitespace or punctuation, with no single mark inside. Kept for callers; the
#: parsers pair single marks by context instead (:func:`_single_quote_spans`), so a quotation whose
#: words carry an apostrophe ('I don't know') is still one quotation.
SINGLE_QUOTE_SPAN_RE = re.compile(
    r"(?:(?<=[\s(\[—–-])|^)'([^'\n]{2,}?[^\s'])'(?=[\s.,;:!?)\]]|$)"
    r"|(?:(?<=[\s(\[—–-])|^)\u2018([^\u2019\n]{2,}?[^\s\u2019])\u2019(?=[\s.,;:!?)\]]|$)"
)
#: A JSON key followed by a JSON value (``"status": "ACCEPTED"``, ``"count": 3``): the shape of a
#: pasted receipt or payload, not of prose (``the noun "command": here`` has no JSON value).
JSON_KEY_RE = re.compile(r'"[A-Za-z_][A-Za-z0-9_]*"\s*:\s*(?:"|-?\d|true\b|false\b|null\b|\{|\[)')
#: A block of lines that opens with ``{`` or ``[`` and closes with the matching bracket
#: without crossing a blank line: machine output pasted into the answer. Kept as the definition of a block: the package reads
#: the blocks with :func:`_json_block_spans`, which gives this pattern's matches in linear time (a search of the pattern reads
#: lazily to the next blank line from every line that opens with a bracket, n² steps on lines of unclosed brackets).
JSON_BLOCK_RE = re.compile(r"^[ \t]*[\[{](?:[^\n]|\n(?![ \t]*\n))*?[\]}][ \t]*$", re.MULTILINE)
#: A line that opens with ``{`` or ``[`` (blanks before it allowed): every block of :data:`JSON_BLOCK_RE` starts at one.
_JSON_BLOCK_START_RE = re.compile(r"^[ \t]*+[\[{]", re.MULTILINE)
#: A closing bracket with nothing but blanks after it on its line: where a block of :data:`JSON_BLOCK_RE` can close.
_JSON_BLOCK_CLOSE_RE = re.compile(r"[\]}][ \t]*+$", re.MULTILINE)
#: A line break before a blank line: a block of :data:`JSON_BLOCK_RE` never crosses one.
_BLANK_LINE_BREAK_RE = re.compile(r"\n(?=[ \t]*+\n)")

#: The specialist labels dates, figures or quotations as unverified recollection.
MEMORY_LABEL_RE = re.compile(
    r"\bfrom (?:memory|recollection)\b|\billustrative\b|\bverify (?:them|these|this|it)\b|\bcheck (?:them |these |this )?(?:against )?your notes\b",
    re.IGNORECASE,
)
#: A note about the task setting rather than the subject: the syllabus version, cohort or level was not given, so no
#: mark or band is implied. IB specialists are required to say so; the sentence is not part of the argument.
TASK_NOTE_RE = re.compile(
    r"\b(?:syllabus|cohort|version|level|mark(?:ing)?|band|grade)s?\b[^.;]{0,80}\b(?:not (?:stated|given|specified|provided|known)|unknown|unstated)\b"
    r"|\bno (?:mark|band|grade)(?: or (?:mark|band|grade))? (?:is|was|can be) (?:given|implied|awarded|assigned)\b",
    re.IGNORECASE,
)
_CHECK_WORDS = r"(?:accurate|correct|reliable|checked|verified|confirmed|validated|double[- ]checked|cross[- ]checked|re[- ]?checked|compared (?:with|against))"
_ANSWER_ITSELF = (r"(?:this (?:paragraph|answer|response|text|essay|report|outline|summary)|all of the above|the above|the foregoing|everything above"
                  r"|the (?:argument|analysis|answer|paragraph|reasoning|claims?|points?) (?:above|here))")
_ITEMS = r"(?:figures?|dates?|quotations?|quotes?|claims?|statistics?|numbers?|statements?|facts?|citations?|references?)"
#: Every item of the answer: "every figure", "all of these figures", "each one of the quotations", "every date and figure in this paragraph".
_EVERY_ITEM = (rf"(?:every|each|all)(?: one)?(?: of (?:the|these|those|my|our|its))? {_ITEMS}(?:,? (?:and|or) {_ITEMS})*"
               rf"(?: (?:in|of|from) (?:this|the) (?:paragraph|answer|response|text|essay|above))?")
#: The answer's items located in the answer itself: "the figures here", "these dates above", "the quotations given here".
_ANCHORED_ITEMS = (rf"(?:the|these|those|my|our|all the|all these) {_ITEMS}(?:,? (?:and|or) {_ITEMS})*"
                   r" (?:here|above|below|(?:given|cited|stated|quoted|used) (?:here|above|below)|in this (?:paragraph|answer|response|essay|text))")
_COPULA = r"(?:is|are|was|were|has been|have been|has now been|have now been)\s+(?:all\s+|fully\s+|carefully\s+|now\s+|independently\s+)?"
#: The verification infrastructure itself (an agent claiming that the engine, the solver or the hub already passed its answer).
_INFRASTRUCTURE = (r"(?:\bz3\b|\b(?:the\s+)?(?:(?:verification|logic|formal|z3|translation|integrity)\s+)?(?:engine|solver|verifier|checker)\b"
                   r"|\b(?:the\s+)?(?:verification|integrity|formal)\s+(?:checks?|layer|pipeline)\b|\bthe\s+(?:hub|channel|translator|overseer|router|combinator)\b)")
#: A receipt or engine status word, in capitals (a vote that "was accepted" is history, not a receipt).
#: (the Language B courses' own status words in capitals too, "VERIFICADO:", "COMPROBADO": round 9, c2 sp-t15-selfcert-es)
_STATUS_WORD = r"(?:VERIFIED|ACCEPTED|REJECTED|ENTAILED|COUNTEREXAMPLE|VERIFICADO|VERIFICADA|COMPROBADO|COMPROBADA|CONFIRMADO|CONFIRMADA|VALIDADO|VALIDADA|REVISADO|REVISADA)"
#: A status word written as a label (integration gate 3): opening the sentence before a colon, a dash, a stop, a bracket, "by" or the end
#: ("VERIFIED: all claims ...", "VERIFIED by the Z3 engine: ...", "ENTAILED."), bracketed alone or after a key ("(ENTAILED)", "[engine:
#: VERIFIED]", "(hub verdict: ENTAILED)"), the value of a status key that opens the sentence or follows a separator ("Status: VERIFIED",
#: "Z3: ENTAILED", "Expected: ENTAILED", "...; Hub verdict: ACCEPTED") or closing the sentence after a semicolon or a dash ("... —
#: VERIFIED."). Elsewhere a capital status word is content until the sentence frames it as the answer's (:data:`_FRAMED_CERT_RE`: "All
#: claims: VERIFIED." is framed by its items) and "it prints VERIFIED", "the program prints Status: VERIFIED", "otherwise result =
#: REJECTED" and "the routine prints: ACCEPTED." are a program's output. Every run is possessive and every repetition bounded.
_STATUS_LABEL = (rf"^[\W_]*+{_STATUS_WORD}\b(?=\s*+(?:[:.!—–(\[]|-\s|$|by\b))"
                 rf"|[\[(]\s*+(?:[A-Za-z][\w'’ -]{{0,40}}?:\s*+)?{_STATUS_WORD}\s*+[.!]?\s*+[\])]"
                 rf"|(?:^[\W_]*+|[;—–]\s*+)(?i:status|result|verdict|outcome|expected|receipt|engine|z3|smt|solver|verifier|checker|hub|overseer|router|channel"
                 rf"|transmission|audit|qa)(?:['’]s)?(?:\s++(?i:status|result|verdict|outcome|decision|check))?\s*+:\s*+{_STATUS_WORD}\b"
                 rf"|(?:[;—–]|\s-\s)\s*+{_STATUS_WORD}\s*+[.!]?[\s\"'”’)\]]*+$")
#: Verification-status vocabulary in the body that is always a self-report: an agent imitating a channel receipt or an engine
#: status (a receipt status, a status word written as a label, "Findings: none", "Transmission ACCEPTED", a receipt's JSON fields, a
#: "Status: ok" that opens the sentence or follows a separator; "the program prints Status: VERIFIED" is a program's output) or
#: certifying the answer itself or its items ("every figure in this paragraph is accurate", "all of the above has been
#: cross-checked": the subject immediately followed by a copula and a checking or accuracy word, so that an argument about what a
#: court "is correct" to do is not a self-report). Phrases are matched case-insensitively. The words that are also ordinary content of
#: the subjects (a capital status word elsewhere, "no findings", "checked and confirmed", "cross-checked", "approved by the overseer",
#: "via branch") are :data:`_FRAMED_CERT_RE`'s, read by :func:`self_cert_vocabulary` (integration gate 3).
SELF_CERT_RE = re.compile(
    rf"\b(?:ACCEPTED_WITH_FINDINGS|INCONSISTENT_PREMISES)\b|{_STATUS_LABEL}"
    r"|(?i:\ball (?:claims|dates|figures|facts|quotations)(?: and (?:figures|dates|quotations))?(?: (?:have been|were|are|was|is))? ?(?:checked|verified|confirmed|validated)\b"
    r"|\bverification (?:complete|passed|status)\b|\bcompared (?:with|against) the supplied\b"
    r"|\bfindings:\s*none\b|\btransmission (?:accepted|rejected)\b|(?:^[\W_]*+|[;—–(\[]\s*+)status:\s*+(?:entailed|accepted|rejected|verified|ok)\b"
    r"|(?:\"|\b)(?:status|receipt_id|transmission_id|formal_checks|structural_findings|findings|codes)\"\s*:"
    rf"|\b{_ANSWER_ITSELF}(?: (?:is|are|was|were|has been|have been)|,? (?:which|and) (?:is|are|has been|have been))\s+(?:all\s+|fully\s+|carefully\s+|now\s+)?{_CHECK_WORDS}\b"
    rf"|\b{_EVERY_ITEM}\s+{_COPULA}{_CHECK_WORDS}\b)",
)
#: Verification-status words that are also ordinary content of the subjects (integration gate 3, the round-2 frame rule of the
#: channel's INT-REQ-014 applied here): a capital status word that is no label ("If they match it prints VERIFIED", "returns
#: REJECTED"), "no findings" ("the inquiry made no findings of a wider conspiracy"), "<verb> by the overseer/translator/hub/engine"
#: ("Every punishment was approved by the overseer"), "checked and confirmed", "cross-checked", "double-checked", "fact-checked",
#: "self-certified", "matches it exactly" and "via branch <word>" ("via branch lines"). Each is a self-certification only in a frame
#: (:func:`self_cert_vocabulary`).
_FRAMED_CERT_RE = re.compile(
    rf"\b{_STATUS_WORD}\b"
    r"|(?i:\b(?:verified|checked|confirmed|validated|proved|proven|accepted|certified|approved) by (?:the )?(?:(?:verification|logic|formal|z3) )?(?:z3|engine|solver|verifier|translator|overseer|hub)\b"
    r"|\bfact[- ]?checked\b|\bself[- ]?certif\w*|\bchecked and confirmed\b|\bdouble[- ]checked\b|\bcross[- ]checked\b"
    r"|\bmatch(?:es|ed)? (?:it|them) exactly\b|\bno findings\b|\bvia branch \w+\b)",
)
#: A finding code of the hub's families ("INT-SUBJ-001", "CORE-SELF-001") or a receipt's field ("formal_checks", "the transmission receipt"):
#: router-side check output, which frames every status word of its sentence as a receipt's.
_RECEIPT_FRAME_RE = re.compile(r"\b(?:INT|CORE|OVS|ST|KIT|ARG|EVD|PACK|BR|GEN|HI|ES|PS|EC|BM)-[A-Z]{2,10}-\d{3}\b"
                               r"|(?i:\b(?:receipt_id|transmission_id|formal_checks|structural_findings|advisory_verification_status)\b"
                               r"|\b(?:transmission|hub(?:'s|’s)?)\s++receipts?\b)")
#: Where a clause ends for a framed word and the subject that frames it: a semicolon, a bracket, a dash, or a comma before a clause of its
#: own ("..., which made no findings", "..., but ..."): "Every figure here comes from the census, which made no findings of fraud" is
#: content.
_CERT_CLAUSE_BREAK_RE = re.compile(r"[;()\[\]—–]|,(?=\s*+(?:which|who|whom|whose|where|when|while|whereas|because|since|although|though|but|yet|so|if|unless)\b)"
                                   r"|\b(?:because|although|though|whereas|unless)\b", re.IGNORECASE)
#: What a sentence that is nothing but a framed word may hold besides it: punctuation, "all", "everything" and auxiliaries and adverbs
#: ("No findings.", "Cross-checked.", "All approved by the hub.", "Everything was checked and confirmed.").
_CERT_FILLER_RE = re.compile(r"[\W\d_]++|\b(?:all|everything|now|fully|formally|independently|again|also|already|thoroughly|carefully|been|has|have|is|are"
                             r"|was|were)\b", re.IGNORECASE)
#: A framed word written as a label on content: opening the sentence before a colon or a dash ("Approved by the overseer: ..."), bracketed
#: ("(no findings)"), or closing it after a separator or ", as" ("...; approved by the hub.", "..., as approved by the overseer.").
_CERT_LEAD_RE = re.compile(r"[\W_]*+")
_CERT_LEAD_TAIL_RE = re.compile(r"\s*+(?::|[—–]|-\s)")
_CERT_TRAIL_BEFORE_RE = re.compile(r"(?:[;—–]|\s-|,\s*+as)\s*+$", re.IGNORECASE)
_CERT_TRAIL_AFTER_RE = re.compile(r"\s*+[.!]?[\s\"'”’)\]]*+$")
_CERT_OPEN_BRACKET_RE = re.compile(r"[\[(]\s*+$")
_CERT_CLOSE_BRACKET_RE = re.compile(r"\s*+[.!]?\s*+[\])]")


def _framed_label(sentence: str, m: "re.Match[str]", lead_end: int) -> bool:
    """The framed word ``m`` stands where a label stands (:data:`_CERT_LEAD_RE` and its neighbours): before content with a colon or a
    dash, bracketed, or at the end after a separator. ``lead_end``: where the sentence's words start. Each test reads a bounded window."""
    if m.start() == lead_end and _CERT_LEAD_TAIL_RE.match(sentence, m.end()):
        return True
    window = sentence[max(0, m.start() - 12):m.start()]
    if _CERT_OPEN_BRACKET_RE.search(window) and _CERT_CLOSE_BRACKET_RE.match(sentence, m.end()):
        return True
    return bool(_CERT_TRAIL_BEFORE_RE.search(window) and _CERT_TRAIL_AFTER_RE.match(sentence, m.end()))


def _framed_self_cert(sentence: str) -> Optional[str]:
    """The first word of :data:`_FRAMED_CERT_RE` in ``sentence`` that its frame makes a self-certification, or None (integration gate 3):
    the answer itself or its items in the same clause (:data:`_SELF_SUBJECT_RE`: "This answer was approved by the overseer", "Every figure
    here was cross-checked", "No findings were raised on the figures above"), the writer narrating its own check ("I double-checked the
    figures"), a finding code or a receipt field in the sentence, or a sentence that is nothing but the word ("No findings.", "Approved by
    the hub."). A word under negation or a deontic modal ("This answer has not been cross-checked") is a disclaimer. Each list is read
    once and every clause is found by bisection, so the work is linear in the sentence."""
    found = [m for m in _FRAMED_CERT_RE.finditer(sentence) if not _NEGATED_OR_DEONTIC_RE.search(sentence[max(0, m.start() - 60):m.start()])]
    if not found:
        return None
    if _RECEIPT_FRAME_RE.search(sentence) is not None or _FIRST_PERSON_CHECK_RE.search(sentence) is not None:
        return found[0].group(0)
    if not _CERT_FILLER_RE.sub("", _FRAMED_CERT_RE.sub(" ", sentence)).strip():
        return found[0].group(0)  # nothing but the framed words: a label of its own
    lead_end = _CERT_LEAD_RE.match(sentence).end()
    for m in found:
        if _framed_label(sentence, m, lead_end):
            return m.group(0)
    subjects = [s.span() for s in _SELF_SUBJECT_RE.finditer(sentence)]
    if not subjects:
        return None
    breaks = [b.start() for b in _CERT_CLAUSE_BREAK_RE.finditer(sentence)]
    for m in found:
        i = bisect.bisect_right(breaks, m.start()) - 1
        lo = breaks[i] if i >= 0 else 0
        j = bisect.bisect_left(breaks, m.end())
        hi = breaks[j] if j < len(breaks) else len(sentence)
        k = bisect.bisect_left(subjects, (lo, -1))
        if k >= len(subjects) or subjects[k][1] > hi:
            continue  # no item of the answer in the clause
        if m.group(0).isupper() and subjects[k][1] > m.start() and _INFRASTRUCTURE_RE.search(sentence, lo, hi) is None:
            # a capital status word is the answer's when its items stand before it ("All figures VERIFIED") or the clause names the
            # system that would have returned it ("The engine returned ENTAILED for every claim here"); "The program prints ACCEPTED
            # if all numbers are valid" is a program's output
            continue
        return m.group(0)
    return None


# ---- self-reports written in Spanish (Language B answers, c1 breadth findings F29 and 17): the shape of the English rules in the
# answer's language. A universal subject ("todas las cifras", "cada una de las respuestas", "todo lo anterior") or the answer itself
# ("esta respuesta") with a copula and a checking participle or an accuracy adjective ("han sido comprobadas", "son correctas") is a
# self-report whoever is said to have checked ("por el Instituto Regional de Estadística": the very note a text may plant); a definite
# or demonstrative subject ("las cifras", "estas respuestas") only with a perfect or present copula and a participle credited to no
# one else ("las cifras fueron comprobadas por el instituto en 2015" is the text's history). A negation or a modal before the copula
# ("no han sido comprobadas", "deben ser comprobadas") never matches: the copula must follow the subject. Possessive blank runs.
_ES_ITEMS = (r"(?:cifras?|respuestas?|datos?|c[áa]lculos?|resultados?|fechas?|citas?|n[úu]meros?|operaciones?|figuras?|valores?|afirmaciones?"
             r"|hechos|cantidades|porcentajes?|soluciones?)")
_ES_PARTICIPLE = r"(?:comprobad|verificad|confirmad|revisad|validad|contrastad|chequead|cotejad)[oa]s?"
_ES_ACCURACY = r"(?:correct[oa]s?|exact[oa]s?|fiables?|precis[oa]s?)"
_ES_COPULA = r"(?:han\s++sido|ha\s++sido|han\s++quedado|ha\s++quedado|est[áa]n|est[áa]|son|es|quedan|queda|fueron|fue)"
_ES_ADVERBS = r"(?:(?:tod[oa]s|ya|debidamente|cuidadosamente|plenamente|totalmente|completamente|independientemente|rigurosamente|tambi[ée]n)\s++)*+"
_ES_ANCHOR = (r"(?:\s++(?:anteriores|de\s++arriba|de\s++(?:esta|mi|la)\s++respuesta|aqu[íi]|presentad[oa]s|citad[oa]s|indicad[oa]s"
              r"|utilizad[oa]s|dad[oa]s))?")
_ES_UNIVERSAL = r"(?:tod[oa]s\s++(?:l[oa]s\s++|est[oa]s\s++|mis\s++)?|cada\s++(?:un[oa]\s++de\s++(?:l[oa]s|est[oa]s|mis)\s++)?)"
_ES_DEFINITE = r"(?:l[oa]s|est[oa]s|mis|nuestr[oa]s)\s++"
#: The answer itself, named as the writer's own ("esta respuesta", "mi respuesta", "todo lo anterior"); "la respuesta" may be the answer
#: to a question of the text ("La respuesta es correcta: ..."), so it is none.
_ES_ANSWER = (r"(?:(?:esta|mi)\s++respuesta|todo\s++lo\s++anterior|todo\s++(?:esto|ello)|el\s++(?:texto|an[áa]lisis|trabajo|resumen)"
              r"\s++(?:anterior|de\s++arriba)|(?:este|mi)\s++(?:texto|art[íi]culo|trabajo|an[áa]lisis|resumen)|esta\s++(?:redacci[óo]n|carta))")
_ES_SELF_REPORT_RE = re.compile(
    rf"\b(?:{_ES_UNIVERSAL}{_ES_ITEMS}{_ES_ANCHOR}|{_ES_ANSWER})\s++{_ES_COPULA}\s++{_ES_ADVERBS}(?:{_ES_PARTICIPLE}|{_ES_ACCURACY})\b"
    rf"|\b{_ES_DEFINITE}{_ES_ITEMS}{_ES_ANCHOR}\s++(?:han\s++sido|ha\s++sido|est[áa]n|son)\s++{_ES_ADVERBS}{_ES_PARTICIPLE}\b(?!\s++por\b)",
    re.IGNORECASE)
#: Cheap pre-filter for the Spanish rule: one of its participles or adjectives must occur.
_ES_CUE_RE = re.compile(r"comprobad|verificad|confirmad|revisad|validad|contrastad|chequead|cotejad|correct[oa]s?\b|exact[oa]s?\b|fiables?\b"
                        r"|precis[oa]s?\b", re.IGNORECASE)


def self_cert_vocabulary(sentence: str) -> Optional[str]:
    """The verification-status vocabulary of ``sentence`` that makes it an agent's self-certification or a receipt imitation, or None:
    a word of :data:`SELF_CERT_RE` anywhere, or a word of :data:`_FRAMED_CERT_RE` in a frame (:func:`_framed_self_cert`; integration gate
    3: ordinary subject content such as "If they match it prints VERIFIED", "the inquiry made no findings", "Every punishment was approved
    by the overseer" or "The deal was checked and confirmed by the competition authority" is no self-certification). The CORE-SELF-001
    pack check and :func:`is_self_certification` read this one rule."""
    if not sentence:
        return None
    m = SELF_CERT_RE.search(sentence)
    if m is not None:
        return m.group(0)
    if len(sentence) <= _CACHE_MAX_CHARS and _ES_CUE_RE.search(sentence):
        m = _ES_SELF_REPORT_RE.search(mask_quotations(sentence))
        if m is not None:
            return sentence[m.start():m.end()]  # the masked text keeps every offset
    return _framed_self_cert(sentence)
#: The looser semantic rule of :func:`is_self_certification`: the sentence speaks of the answer
#: itself (or of every figure, date or quotation in it, or of its items "here" or "above") and,
#: anywhere in the sentence, of a checking act, of the reader relying on it, of its quotations
#: appearing verbatim, of no errors being found, or of the verification infrastructure passing
#: it. A bare accuracy adjective ("is correct") counts only right after such a subject ("the
#: figures here are accurate", "every one of them is correct"), so "this paragraph argues that
#: the court is correct to uphold the thesis" stays an argument. Only a POSITIVE predicate
#: counts: a check under negation or a deontic modal ("have not been checked", "should be
#: checked before they are cited", "must be verified", "unverified") is a disclaimer, the
#: opposite of a self-certification, and is read as a from-memory label instead.
_SELF_SUBJECT_RE = re.compile(rf"\b(?:{_ANSWER_ITSELF}|{_EVERY_ITEM}|{_ANCHORED_ITEMS})\b", re.IGNORECASE)
_SELF_PREDICATE_RE = re.compile(
    r"\b(?:checked|verified|confirmed|validated|double[- ]checked|cross[- ]checked|re[- ]?checked|compared (?:with|against))\b"
    r"|\bmatch(?:es|ed)? (?:it|them|the \w+(?: \w+)?) (?:exactly|precisely|word for word|verbatim)\b"
    r"|\bappear(?:s|ed)? (?:verbatim|word for word|exactly as (?:written|printed|given))\b|\b(?:is|are) verbatim\b"
    r"|\brely (?:on|upon) (?:it|them|these|this)\b|\b(?:may|can) be relied (?:on|upon)\b|\bcan be trusted\b|\btrustworthy\b|\berror[- ]free\b|\bfree of errors?\b"
    r"|\bno (?:errors?|mistakes?|inaccuracies|problems)\s+(?:were|was|have been|has been|are|is)\s+(?:found|detected|identified|present)\b",
    re.IGNORECASE,
)
#: A checking predicate under negation or a deontic modal: the words just before it make it a disclaimer. So does the reader's own
#: reliance made conditional on a check the reader is told to make ("check them against your textbook before you rely on them";
#: round-9 clearance c2b, hi-t15 h1.19: a caveat, never an assurance).
_NEGATED_OR_DEONTIC_RE = re.compile(
    r"(?:\bnot|\bnever|n['’]t|\bcannot|\bno longer|\byet to|\bstill to)\s+(?:\w+\s+){0,3}$"
    r"|\b(?:should|must|needs?\s+to|ought\s+to|has\s+to|have\s+to|had\s+to|are\s+to|is\s+to|to)\s+(?:(?:still|first|all|each|independently|carefully|also|then|now)\s+)*(?:have\s+)?(?:be|been)\s+(?:\w+ly\s+)?$"
    r"|\b(?:before|until|unless|if|once)\s+(?:you|students?|the\s+(?:reader|student))\s+(?:\w+\s+){0,2}$",
    re.IGNORECASE,
)
#: An accuracy adjective right after a self-subject (or "every one of them"): "the figures here are correct to the nearest tenth".
_SELF_ACCURACY_RE = re.compile(
    rf"\b(?:{_ANSWER_ITSELF}|{_EVERY_ITEM}|{_ANCHORED_ITEMS}|(?:every|each|all)(?: one)? of (?:them|these|those))\s+"
    r"(?:is|are|was|were)\s+(?:all\s+|entirely\s+|fully\s+|completely\s+)?(?:accurate|correct|reliable|error[- ]free)\b",
    re.IGNORECASE,
)
#: The writer narrating its own check: "I have checked ...", "I verified each figure", "we have confirmed".
_FIRST_PERSON_CHECK_RE = re.compile(
    r"(?:\bI|\b[Ww]e)(?:\s+have|['’]ve|\s+had)?\s+(?i:(?:(?:now|also|personally|carefully|independently|already|just|thoroughly|individually|myself)\s+)*"
    r"(?:checked|verified|confirmed|validated|double[- ]checked|cross[- ]checked|fact[- ]checked|re-?checked))\b"
)
_INFRASTRUCTURE_RE = re.compile(_INFRASTRUCTURE, re.IGNORECASE)
_INFRASTRUCTURE_VERB_RE = re.compile(
    r"\b(?:prov(?:ed|en|es)|verif(?:ied|ies)|confirm(?:ed|s)|accept(?:ed|s)|validat(?:ed|es)|entail(?:ed|s)|certif(?:ied|ies)|approv(?:ed|es)|signed off|passed)\b",
    re.IGNORECASE,
)
#: A year, a capitalised month name (``may`` the modal verb is not a month) or a figure with a unit.
_DATED_ITEM_RE = re.compile(
    r"\b(?:1[0-9]{3}|20[0-9]{2})\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b"
    r"|(?i:\b\d+(?:[.,]\d+)?\s*(?:per cent|percent|%|million|billion|thousand)\b)",
)

# ---- the structural self-certification rule (:func:`is_self_certification`): a SUBJECT that refers to the answer or to
# its own items, followed by a PREDICATE that certifies them. Decided by the shape of the clause, not by listed sentences.
#: The answer's own items. "lines" counts only as "quoted/cited lines" (a poem's lines are the text, not the answer's items).
_SELF_ITEMS = (r"(?:figures?|dates?|quotations?|quotes?|claims?|statistics?|numbers?|statements?|facts?|citations?|references?|excerpts?"
               r"|totals?|estimates?|details?|items?|(?:quoted|cited) lines?"
               # the answer's own working and results ("All calculations above were checked ...", "All working above is verified
               # correct."; c1 breadth finding 17): an accuracy adjective alone never certifies them (:data:`_ACC_ITEM_RE`)
               r"|calculations?|computations?|workings?|arithmetic|answers?|results?|steps?|solutions?|sums?)")
#: The items whose accuracy a bare adjective can certify ("these figures are accurate"); "these claims are reliable" may be
#: a historian weighing a source, so claims, statements, facts and details need a checking predicate instead.
_ACC_ITEM_RE = re.compile(r"(?:figures?|dates?|quotations?|quotes?|statistics?|numbers?|citations?|references?|excerpts?|totals?|(?:quoted|cited) lines?)\W*$",
                          re.IGNORECASE)
#: Up to two plain modifiers between a determiner and an item noun ("every mileage figure", "the key dates"); a modifier is
#: never a verb, an auxiliary, a preposition, a conjunction or an anchor word.
_SELF_MOD = (r"(?:(?!(?:is|are|was|were|has|have|had|been|be|being|and|or|but|nor|of|in|on|at|to|for|from|with|by|that|which|who|here"
             r"|above|below|given|not|no|as|than|so|its|it|this|these|those|the|a|an)\b)[a-z][a-z'’-]*\s+){0,2}")
#: Where the answer locates its own items: "here", "above", "given above", "in this answer", "of the paragraph above".
_SELF_ANCHOR = (r"(?:here|above|below|(?:given|cited|stated|quoted|used|listed|presented|included|offered|mentioned|provided|reproduced|set out)"
                r"\s+(?:here|above|below|in\s+(?:this|my|the)\s+(?:paragraph|answer|response|essay|analysis|outline|summary))"
                r"|in\s+(?:this|my)\s+(?:paragraph|answer|response|essay|analysis|outline|summary|report)|(?:in|of)\s+the\s+(?:paragraph|answer|response|essay)\s+above)")
_SELF_ITEM_LIST = rf"{_SELF_MOD}{_SELF_ITEMS}(?:,?\s+(?:and|or)\s+{_SELF_MOD}{_SELF_ITEMS})*"
_SELF_UNIVERSAL_DET = r"(?:every|each(?:\s+one)?(?:\s+of\s+(?:the|these|those|my|our|its))?|all(?:\s+(?:of\s+)?(?:the|these|those|my|our|its))?)"
#: The answer itself, as the writer names it: "this paragraph", "the argument above", "my reading", "the whole answer".
_SELF_ANSWER = (rf"(?:{_ANSWER_ITSELF}|(?:my|our)\s+(?:own\s+)?(?:reading|argument|answer|analysis|interpretation|paragraph|essay|response|account"
                r"|outline|summary|conclusion|judge?ment|work)|(?:the|this)\s+(?:whole|entire)\s+(?:answer|paragraph|response|essay|analysis|argument))")
#: A received report or a supplied text named as the source of the answer's items: "the History specialist", "the History
#: report", "that account", "the poem", "both texts", "the supplied extract". A report source qualifies any item; a text
#: source only quotations (the poem's "figures" may be figures of speech).
_SOURCE_REPORT = (r"(?:(?:the|my|our)\s+(?:[a-z]+\s+)?(?:specialist|colleague|peer)(?:(?:'s|’s)\s+(?:paragraph|report|account|answer|analysis))?"
                  r"|(?:the|that|this|its)\s+(?:history|english|peer|colleague['’]s|specialist['’]s|relayed|received)\s+(?:report|account|paragraph|answer))")
_SOURCE_TEXT = (r"(?:(?:the|both|each|all\s+the|these)\s+(?:(?:supplied|source|original|given)\s+)?(?:poem|poems|sonnet|texts?|extracts?|passages?|novel|play|story)"
                r"|(?:the|both)\s+(?:supplied|source|original|given)\s+(?:texts?|documents?))")
#: The participle or preposition that ties an item to its source: "of", "from", "taken from", "quoted from".
_SOURCE_LINK = r"(?:of|from|(?:taken|quoted|drawn|reproduced|copied|cited|borrowed|lifted)\s+from)"
_QUOTE_ITEMS = r"(?:quotations?|quotes?|excerpts?|citations?|(?:quoted|cited)\s+lines?)"
#: Items of the answer named with the source they were taken from, optionally anchored: "each quotation of the History
#: specialist above", "all quotations from the History specialist above", "the quotations of the poem above", "my
#: quotations of both texts", "the quotations from the History report", "every figure taken from the History specialist".
_SELF_SOURCED = (rf"(?:{_SELF_UNIVERSAL_DET}\s+|(?:the|these|those|my|our)\s+)?"
                 rf"(?:{_SELF_ITEM_LIST}\s+{_SOURCE_LINK}\s+{_SOURCE_REPORT}|{_SELF_MOD}{_QUOTE_ITEMS}\s+{_SOURCE_LINK}\s+(?:{_SOURCE_REPORT}|{_SOURCE_TEXT}))"
                 rf"(?:\s+{_SELF_ANCHOR})?")
#: Items named with their source, read in a pass of their own (:func:`_structural_self_report`) and only when the sentence
#: names a source after "of" or "from" (:data:`_SOURCE_CUE_RE`), so the subject scan of every other sentence costs what it did.
_SELF_SOURCED_RE = re.compile(rf"\b(?P<sourced>{_SELF_SOURCED})\b", re.IGNORECASE)
_SOURCE_CUE_RE = re.compile(r"\b(?:of|from)\s+(?:\w+\s+){0,3}?(?:specialist|colleague|peer|report|account|paragraph|answer|poems?|sonnet|texts?|extracts?"
                            r"|passages?|novel|play|story|documents?)\b", re.IGNORECASE)
#: One subject, by kind: anchored items, the answer itself, every item, demonstrative items ("these figures", "my
#: quotations") and bare definite items ("the quotations"). The kind decides which predicates certify
#: (:func:`_structural_self_report`).
_SELF_SUBJECT_KINDS_RE = re.compile(
    rf"\b(?:(?P<anchored>(?:{_SELF_UNIVERSAL_DET}\s+|(?:the|these|those|my|our)\s+)?{_SELF_ITEM_LIST}\s+{_SELF_ANCHOR})"
    rf"|(?P<answer>{_SELF_ANSWER})"
    rf"|(?P<universal>{_SELF_UNIVERSAL_DET}\s+{_SELF_ITEM_LIST})"
    rf"|(?P<demonstrative>(?:these|those|my|our)\s+{_SELF_ITEM_LIST})"
    rf"|(?P<definite>the\s+{_SELF_ITEM_LIST}))\b",
    re.IGNORECASE,
)
#: What follows the subject: a copula, then adverbs, then a checking participle or an accuracy adjective.
_SELF_COPULA = r"\s+(?:is|are|was|were|(?:has|have|had)\s+(?:(?:all|each|now|both|already|also)\s+)?been|remains?)\s+"
_SELF_PERFECT_RE = re.compile(r"\s+(?:is|are|(?:has|have)\s+(?:(?:all|each|now|both|already|also)\s+)?been)\s+", re.IGNORECASE)
_SELF_ADVERBS = (r"(?:(?:all|now|fully|carefully|independently|formally|thoroughly|individually|each|already|also|both|entirely|completely"
                 r"|wholly|perfectly|properly|rigorously|systematically|duly|personally|again)\s+)*")
_SELF_CHECK = (r"(?:checked|verified|confirmed|validated|corroborated|audited|proof-?read|double[- ]checked|cross[- ]checked|fact[- ]checked"
               r"|re-?checked|compared\s+(?:with|against)|matched\s+(?:against|with|to))")
_SELF_ACCURACY = (r"(?:accurate|correct|exact|reliable|sound|right|error[- ]free|verbatim|trustworthy|faithful|free\s+(?:of|from)\s+errors?"
                  r"|without\s+(?:any\s+)?errors?)")
#: Reproduction fidelity: "reproduced exactly", "quoted verbatim", "copied word for word", "transcribed without alteration".
#: Only the writer reproduces the answer's own items, so this certifies whatever the subject's kind.
_SELF_FIDELITY = (r"(?:reproduced|quoted|copied|transcribed|rendered|cited)\s+(?:(?:here|above|below|in\s+full)\s+)?"
                  r"(?:exactly|verbatim|word\s+for\s+word|letter\s+for\s+letter|faithfully|accurately|precisely|correctly"
                  r"|without\s+(?:any\s+)?(?:change|alteration|error|omission)s?)")
_SELF_PREDICATE_TAIL_RE = re.compile(
    rf"{_SELF_COPULA}{_SELF_ADVERBS}(?:(?P<fidelity>{_SELF_FIDELITY})|(?P<check>{_SELF_CHECK})|(?P<accuracy>{_SELF_ACCURACY}))\b",
    re.IGNORECASE,
)
#: An accuracy adjective that closes the clause ("these figures are accurate.", "... are reliable and need no further
#: checking"): "these figures are reliable because the Board of Trade ..." is a historian weighing a source, not a self-report.
#: The blank runs are possessive and the optional comma is read with the blanks before it (integration gate 2): ``\s*,?\s+`` split a run
#: of blanks after the adjective in every way before failing, k² steps for each subject read (0.2 s at 4,000 blanks).
_SELF_CLOSING_RE = re.compile(
    r"\s*+(?:[.;!:)\]\"'”’]|$|,\s++(?:and|so)\s+(?:can|may|might|could|need|needs|require|requires|has|have|is|are|was|were|match|matches"
    r"|appear|appears|contain|contains|so|the\s+reader)\b)"
    r"|\s++(?:and|so)\s+(?:can|may|might|could|need|needs|require|requires|has|have|is|are|was|were|match|matches"
    r"|appear|appears|contain|contains|so|the\s+reader)\b",
    re.IGNORECASE,
)
#: A check credited to an agent that is neither the writer nor the infrastructure ("my reading is confirmed by the final
#: stanza", "these figures were checked by the Registrar General"): an argument about evidence, not a self-report.
_BY_OTHER_AGENT_RE = re.compile(
    rf"\s+by\s+(?!(?:me|myself|us|ourselves|the\s+(?:writer|author|specialist)|this\s+specialist|{_INFRASTRUCTURE})\b)",
    re.IGNORECASE,
)
#: Nothing further to check: "need no further checking", "require no verification", "need not be checked", "no further
#: checking is needed".
_NO_FURTHER_CHECK_RE = re.compile(
    r"\b(?:needs?|requires?|calls?\s+for|merits?|warrants?)\s+no\s+(?:further\s+|more\s+|additional\s+|other\s+|independent\s+)?"
    r"(?:check(?:ing|s)?|verification|verifying|confirmation|correction|cross[- ]checking)\b"
    r"|\bneed\s+not\s+be\s+(?:re-?)?(?:checked|verified|confirmed)\b"
    r"|\b(?:do|does)\s+not\s+need\s+(?:to\s+be\s+)?(?:further\s+|any\s+)?(?:re-?)?(?:checked|checking|verified|verifying|verification|confirmed)\b"
    r"|\bno\s+(?:further\s+|more\s+|additional\s+)?(?:check(?:ing|s)?|verification|confirmation)\s+(?:is|are|was|were)\s+(?:needed|required|necessary)\b"
    r"|\bbeyond\s+(?:the\s+need\s+(?:for|of)\s+)?(?:checking|verification)\b",
    re.IGNORECASE,
)
#: "Nothing in this answer needs checking", "none of the figures above needs checking", "no quotation here requires checking".
_NOTHING_NEEDS_CHECK_RE = re.compile(
    rf"\b(?:nothing\s+(?:else\s+)?(?:(?:in|of)\s+(?:this|my|the)\s+(?:paragraph|answer|response|essay|analysis|argument|outline|report|summary)|here|above)"
    rf"|none\s+of\s+(?:it|this|these|those|the\s+above|(?:the|these|those|my)\s+{_SELF_ITEM_LIST}(?:\s+{_SELF_ANCHOR})?)"
    rf"|no\s+{_SELF_ITEM_LIST}\s+{_SELF_ANCHOR})"
    r"\s+(?:needs?|requires?|calls?\s+for|merits?|warrants?)\s+(?:any\s+|further\s+|more\s+)?(?:check(?:ing)?|verification|correction|to\s+be\s+(?:re-?)?(?:checked|verified))\b",
    re.IGNORECASE,
)
#: Items matched word for word, or checked against "the supplied" text: a check only the writer reports about its own quotations.
_STRONG_MATCH_RE = re.compile(
    r"\b(?:checked|verified|compared|matched|cross[- ]checked|collated)\s+(?:(?:word\s+for\s+word|verbatim|exactly|letter\s+for\s+letter|line\s+by\s+line"
    r"|character\s+by\s+character|one\s+by\s+one|carefully|individually)\s+)*(?:against|with|to)\s+(?:the\s+)?(?:supplied|original|provided|given)\b"
    r"|\b(?:checked|verified|compared|matched|collated)\s+(?:word\s+for\s+word|verbatim|letter\s+for\s+letter|line\s+by\s+line|character\s+by\s+character)\b",
    re.IGNORECASE,
)
#: A sentence-initial lead that certifies what follows: "As verified, ...", "As checked above, ...", "As confirmed by the
#: engine, ...", "As the hub has confirmed, ...". "As confirmed by Engels, ..." cites a source and is not one. At most one
#: complement ("against the text") and a bounded run of place words, so a lead with no closing comma fails in linear time.
_SELF_LEAD_RE = re.compile(
    rf"^\W*As\s+(?:(?:already|now|formally|independently|previously|carefully|fully)\s+)?"
    rf"(?:{_SELF_CHECK}|proved|proven|certified|accepted|approved)"
    r"(?:\s+(?:above|here|below|earlier|before|already|throughout|in\s+full)){0,3}"
    rf"(?:\s+(?:by\s+{_INFRASTRUCTURE}|(?:against|with)\s+[^,;:.]{{1,60}}))?\s*[,:]"
    rf"|^\W*As\s+{_INFRASTRUCTURE}\s+(?:has\s+|have\s+|had\s+)?(?:already\s+)?(?:verified|checked|confirmed|proved|shown|accepted|certified|validated)\b",
    re.IGNORECASE,
)
# ---- the compliance self-report rule (:func:`is_self_certification`): the answer, its quotations or the request's items as
# subject, a predicate saying that the answer satisfies the request ("is under the word limit", "meets every constraint",
# "complies with the router's instructions", "are addressed above", "follow the 1633 spelling of the supplied text"), and a
# word-count line ("Word count: 258.", "258 words."). The sentence must open on the subject and say nothing else, so "The
# poem answers every question the speaker asks" and "The paragraph argues that ..." stay arguments; a negated or modal
# predicate ("should stay within the word limit", "is not under") never matches.
_COMPLIANCE_LEAD = r"^\W*(?:(?:overall|finally|note|also|in\s+total|in\s+sum|for\s+the\s+record|as\s+requested)\s*[,:]\s*)?"
_COMPLIANCE_ANSWER = (rf"(?:{_SELF_ANSWER}|(?:the|this|my|our)\s+(?:whole\s+|entire\s+|final\s+)?(?:paragraph|answer|response|essay|analysis|outline|summary|reply"
                      r"|submission))")
_COMPLIANCE_ITEMS = (rf"(?:(?:{_SELF_UNIVERSAL_DET}|both|the|my|our|these)\s+)?(?:(?:request|question|task|router['’]s|prompt['’]s|request['’]s|question['’]s)\s+"
                     r"(?:items?|parts?|requirements?|constraints?|instructions?|conditions?|criteria|demands?)"
                     r"|(?:items?|parts?|requirements?|constraints?|instructions?|conditions?|criteria|demands?)\s+of\s+the\s+(?:question|request|task|prompt))")
_COMPLIANCE_QUOTES = rf"(?:(?:{_SELF_UNIVERSAL_DET}|the|my|our|these)\s+)?(?:\w+\s+)?{_QUOTE_ITEMS}(?:\s+{_SELF_ANCHOR})?"
#: "is under the word limit", "stays within the 300-word limit", "is 258 words long", "runs to about 250 words".
_COMPLIANCE_LIMIT = (r"(?:is|are|was|stays?|remains?|keeps?|falls?|sits?|comes?\s+in|runs?)\s+(?:(?:well|comfortably|safely|just|also|exactly|therefore)\s+)?"
                     r"(?:(?:under|within|below|inside|beneath)\s+(?:the\s+|its\s+|a\s+|my\s+)?(?:\d[\d,]*[- ]word\s+|requested\s+|required\s+|stated\s+|set\s+|given\s+|maximum\s+)?"
                     r"(?:word[- ])?(?:limit|count|bound|maximum|length|cap|target|ceiling|allowance)"
                     r"|(?:to\s+)?(?:about\s+|around\s+|roughly\s+|approximately\s+|exactly\s+|only\s+)?\d[\d,]*\s+words(?:\s+long|\s+in\s+(?:total|length))?)"
                     r"|(?:has|contains|uses)\s+(?:about\s+|around\s+|roughly\s+|approximately\s+|exactly\s+|only\s+|fewer\s+than\s+|under\s+)?\d[\d,]*\s+words")
#: "meets every constraint in the request", "answers every part of the question", "complies with the router's instructions".
_COMPLIANCE_MEETS = (r"(?:meets?|satisf(?:ies|y)|fulfil(?:l?s)?|respects?|observes?|obeys?|follows?|honou?rs?|(?:complies|comply)\s+with|conforms?\s+to|adheres?\s+to"
                     r"|answers?|addresses|covers?|(?:keeps?|sticks?)\s+to)\s+"
                     r"(?:(?:each|every|all(?:\s+of)?|both)\s+(?:the\s+|its\s+|of\s+the\s+)?|the\s+|its\s+)(?:[\w'’-]+\s+){0,3}?"
                     r"(?:constraints?|requirements?|instructions?|limits?|parts?|items?|criteria|criterion|conditions?|rules?|questions?|demands?|specifications?"
                     r"|brief|task|request|prompt)")
#: "are addressed above", "have all been answered" (the request's items as subject).
_COMPLIANCE_DONE = (r"(?:is|are|has\s+been|have\s+been)\s+(?:(?:all|each|both|fully|now|also)\s+)?"
                    r"(?:addressed|answered|covered|met|satisfied|fulfill?ed|respected|observed|followed|dealt\s+with|handled)")
#: "follow the 1633 spelling of the supplied text", "keep the original punctuation of the poem".
_COMPLIANCE_SPELLING = (r"(?:follow|keep|retain|preserve|use|reproduce|respect|match)(?:s|es)?\s+(?:the\s+|its\s+)?(?:(?:\d{3,4}|original|exact|source|supplied|old|archaic)\s+)*"
                        r"(?:spellings?|punctuation|wording|lineation|line\s+breaks|capitali[sz]ation|orthography)\s+(?:of|in|used\s+in)\s+(?:the\s+)?"
                        r"(?:supplied|original|given|source|provided|printed)?\s*(?:text|extract|poem|passage|edition|document|sonnet)")
#: What may follow a compliance predicate inside its clause ("in the request", "of the question", "above", "in full").
_COMPLIANCE_TAIL = (r"(?:\s+(?:in|of|for|from|set\s+by|given\s+by|stated\s+in|above|here|in\s+full|as\s+(?:set|stated|given|requested)"
                    r"|as\s+(?:it|they)\s+(?:appears?|stands?|reads?)\s+in)\b[^,;.!?]{0,60})?")
_COMPLIANCE_PRED = rf"(?:{_COMPLIANCE_LIMIT}|{_COMPLIANCE_MEETS}|{_COMPLIANCE_SPELLING}){_COMPLIANCE_TAIL}"
_COMPLIANCE_RE = re.compile(
    rf"{_COMPLIANCE_LEAD}(?:"
    rf"{_COMPLIANCE_ANSWER}\s+{_COMPLIANCE_PRED}(?:\s*,?\s+(?:and|while|but\s+also)\s+(?:it\s+)?{_COMPLIANCE_PRED}){{0,3}}"
    rf"|(?:{_COMPLIANCE_ITEMS})\s+{_COMPLIANCE_DONE}{_COMPLIANCE_TAIL}"
    rf"|{_COMPLIANCE_QUOTES}\s+(?:{_COMPLIANCE_SPELLING}|(?:is|are)\s+(?:all\s+)?{_SELF_FIDELITY}){_COMPLIANCE_TAIL}"
    r")\s*(?:\([^()]{0,40}\)\s*)?[.!]?[\"'”’)\]]*\s*$",
    re.IGNORECASE,
)
#: A word-count line: "Word count: 258.", "258 words.", "(about 250 words)", "Words: 258", "The word count is 258."
_WORD_COUNT_RE = re.compile(
    r"^\W*(?:(?:approximate|approx\.?|total|final|actual|my)\s+)?word[- ]?count\s*(?:[:=—–-]|is|of)?\s*(?:approx(?:imately|\.)?\s+|about\s+|around\s+|roughly\s+|c\.\s*|~\s*)?"
    r"\d[\d,]*(?:\s+words?)?\s*(?:\(\s*approx(?:imately|\.)?\s*\)|\(\s*excluding[^()]{0,40}\))?\W*$"
    r"|^\W*(?:approx(?:imately|\.)?\s+|about\s+|around\s+|roughly\s+|c\.\s*|~\s*)?\d[\d,]*\s+words?(?:\s+(?:in\s+total|total|long|exactly|approx(?:imately|\.)?))?\W*$"
    r"|^\W*(?:total\s+)?words?(?:\s+used)?\s*[:=]\s*\d[\d,]*\W*$"
    r"|^\W*(?:the|my)\s+word[- ]count\s+(?:is|was|comes\s+to)\s+(?:approx(?:imately|\.)?\s+|about\s+|around\s+|roughly\s+)?\d[\d,]*(?:\s+words?)?\W*$",
    re.IGNORECASE,
)
#: A colleague's or the poem's words said to be quoted exactly in the answer: "The History specialist's words are quoted above exactly as delivered."
_QUOTED_WORDS_FIDELITY_RE = re.compile(
    r"^\W*(?:the\s+)?(?:[A-Za-z]+\s+)?(?:specialist|colleague|peer|poem|poet|author|sonnet|extract|speaker)(?:'s|’s)\s+(?:own\s+)?(?:words|figures|quotations?|lines|phrasing|wording|phrases)"
    r"\s+(?:is|are|has\s+been|have\s+been)\s+(?:all\s+)?"
    rf"(?:{_SELF_FIDELITY}|(?:quoted|reproduced|copied|cited|given)\s+(?:here|above)\s+(?:exactly|verbatim|word\s+for\s+word|faithfully|accurately|precisely|correctly))\b",
    re.IGNORECASE,
)
#: The infrastructure as the agent of a certifying verb: "the router has confirmed ...", "Z3 proved ...", "... signed off by the Overseer".
_INFRA_AGENT_RE = re.compile(
    rf"{_INFRASTRUCTURE}(?:\s+(?:has|have|had|already|now|also|itself|formally|independently|fully|duly))*\s+"
    r"(?:prov(?:ed|en|es)|verif(?:ied|ies)|confirm(?:ed|s)|accept(?:ed|s)|validat(?:ed|es)|entail(?:ed|s)|certif(?:ied|ies)|approv(?:ed|es)|signed\s+off|passed|cleared)\b"
    rf"|\b(?:proved|verified|confirmed|accepted|validated|certified|approved|signed\s+off|passed|cleared)\s+by\s+{_INFRASTRUCTURE}",
    re.IGNORECASE,
)
#: What the infrastructure is said to have passed: the answer, its items, "every item", "everything".
_INFRA_OBJECT_RE = re.compile(
    r"\b(?:(?:this|my|our)\s+(?:answer|paragraph|response|report|essay|analysis|argument|reading|submission|work)"
    r"|the\s+(?:answer|paragraph|response|essay|analysis|argument|reading|request|submission)"
    rf"|every(?:thing|\s+(?:item|requirement|point|part|criterion))|all\s+(?:the\s+)?(?:items|requirements|points|parts|criteria))\b",
    re.IGNORECASE,
)
#: Where a check closes for a subject that does not itself name the answer: the clause ends, or the check is made against
#: something, word for word, or before use. "My reading is confirmed when the speaker ..." and "the claims have been
#: verified in later scholarship" go on to argue, and are not self-reports.
_CHECK_END_RE = re.compile(
    r"\s*(?:[.;!:,)\]\"'”’]|$)|\s+(?:against|and|so|before|for\s+accuracy|word\s+for\s+word|line\s+by\s+line|one\s+by\s+one|individually"
    r"|independently|carefully|thoroughly|twice|again|throughout|in\s+full|in\s+every\s+case|with\s+(?:the\s+)?(?:supplied|original|source))\b",
    re.IGNORECASE,
)
#: "the quotations" with no modifier: a bare definite subject, whose accuracy adjective may certify the answer's items.
_BARE_DEFINITE_RE = re.compile(rf"the\s+{_SELF_ITEMS}(?:,?\s+(?:and|or)\s+{_SELF_ITEMS})*", re.IGNORECASE)
#: How firmly a subject named with its source points at the answer's own items (:func:`_sourced_kind`).
_SOURCED_ANCHOR_RE = re.compile(rf"\s{_SELF_ANCHOR}$", re.IGNORECASE)
_SOURCED_QUOTING_RE = re.compile(rf"\b{_QUOTE_ITEMS}\s+{_SOURCE_LINK}\b|\b(?:taken|quoted|drawn|reproduced|copied|cited|borrowed|lifted)\s+from\b", re.IGNORECASE)
#: The determiners that make a subject more than a bare definite one ("every", "these", "my" ...).
_NON_DEFINITE_DETERMINERS = frozenset({"every", "each", "all", "these", "those", "my", "our"})
#: Where a reproduction-fidelity predicate closes for a subject not anchored in the answer: the clause ends, or the item is
#: said to stand as it does in the supplied text ("as it appears in the extract"). "The census figures are reproduced exactly
#: in Mitchell's tables" is a historian's statement about another work, not a self-report.
_FIDELITY_END_RE = re.compile(
    r"\s*(?:[.;!:,)\]\"'”’]|$)|\s+(?:as\s+(?:it|they)\s+(?:appears?|stands?|is|are|was|were|reads?)\b|as\s+(?:written|printed|given|delivered|supplied|received)\b"
    r"|(?:from|in)\s+the\s+(?:supplied|original|source|given)\b|in\s+(?:this|my)\s+(?:answer|paragraph|response|essay)\b|against\b|and\b|so\b|here\b|above\b|throughout\b)",
    re.IGNORECASE,
)


def _quoted_words_fidelity(sentence: str) -> bool:
    """A colleague's or the poem's words said to be quoted exactly in the answer (:data:`_QUOTED_WORDS_FIDELITY_RE`), the
    predicate closing the clause or saying how the words stand ("... quoted above exactly as delivered."). "The speaker's
    words are quoted exactly by Love." credits the quoting to a figure of the poem and "... reproduced exactly in the final
    line" places the repetition in the text: both are the writer's analysis, not a self-report."""
    m = _QUOTED_WORDS_FIDELITY_RE.match(sentence)
    return m is not None and _FIDELITY_END_RE.match(sentence, m.end()) is not None


def _sourced_kind(subject: str) -> str:
    """How a subject named with its source ("each quotation of the History specialist above", "the figures quoted from the
    History specialist", "the figures of the History report") certifies: ``anchored`` when it is anchored in the answer
    ("above", "here"), ``quoted`` when its items are quotations or were taken by a quoting participle ("quoted from", "taken
    from"), so they are the answer's own reproductions, and ``weak`` otherwise (a report's figures may be weighed, so only a
    checking participle certifies them)."""
    if _SOURCED_ANCHOR_RE.search(subject):
        return "anchored"
    return "quoted" if _SOURCED_QUOTING_RE.search(subject) else "weak"


# ---- the verification-label rule (:func:`verification_label`): a bare verification-status label an agent writes on its
# own text, standing for the whole sentence ("Verified.", "(checked)"), in front of its content ("Verified: ...",
# "[verified] ...", "Fact-checked — ..."), after it ("... (verified).", "..., as formally verified.", "...; checked.") or
# bracketed inside it. Decided by the label's shape, not by listed sentences.
#: The label's checking participle, a compound one included ("source-checked", "spot-checked", "Z3-verified",
#: "formally-verified"). "proved" (a proof's closing word), accuracy adjectives ("correct") and a participle under negation
#: or a modal ("unverified", "not checked", "to be verified") are never a label here on their own.
_LABEL_WORD = (r"(?:verified|checked|confirmed|validated|certified|corroborated|audited|proof-?read|fact[- ]?checked|double[- ]checked"
               r"|triple[- ]checked|cross[- ]checked|re-?checked|re-?verified|(?:source|spot|self|machine|hand)[- ]?(?:checked|verified)"
               r"|(?:z3|engine|solver|hub|formally)[- ](?:checked|verified|proven|proved|confirmed)"
               # the same participles in Spanish, a Language B answer's labels ("VERIFICADO:", "Comprobado.")
               r"|(?:verificad|comprobad|confirmad|validad|revisad|certificad)[oa]s?)")
_LABEL_ADVERB = (r"(?:(?:all|fully|formally|independently|now|already|thoroughly|carefully|individually|externally|manually|automatically"
                 r"|rigorously|duly|personally|each|both|also)\s+)*")
#: Who checked, when the label names it: the infrastructure or the writer ("verified by Z3", "checked by me"); a label
#: credited to anyone else ("confirmed by Engels", "verified by the History specialist") cites a source and is not a
#: self-report.
_LABEL_BY = (rf"(?:\s+by\s+(?:{_INFRASTRUCTURE}|(?:me|myself|us|ourselves|the\s+(?:writer|author|specialist)|this\s+specialist)\b))")
#: What the label says it was checked against: the supplied or source texts, the sources, the specialists' reports, the
#: originals ("checked against the sources", "verified with the specialists' reports", "against the original"). A record
#: the writer names ("checked against the Registrar General's returns") is a citation of the writer's evidence, not one.
_LABEL_AGAINST = (r"(?:\s+(?:against|with)\s+(?:the|all\s+the|each\s+of\s+the|every|its|their|my|our|both)\s+"
                  r"(?:(?:supplied|original|source|given|provided|cited|underlying|relevant)\s+)?(?:specialists?['’]?s?\s+)?"
                  r"(?:texts?|extracts?|documents?|sources?|passages?|poems?|data|figures|reports?|answers?|claims?|originals?|evidence"
                  r"|source\s+claims?)\b)")
_LABEL_PHRASE = (rf"{_LABEL_ADVERB}{_LABEL_WORD}(?:\s*(?:,|&|/|\band\b)\s*{_LABEL_ADVERB}{_LABEL_WORD})*"
                 rf"(?:{_LABEL_BY}{_LABEL_AGAINST}?|{_LABEL_AGAINST}{_LABEL_BY}?)?")
#: A verdict written as a label: a checking or proving participle with an accuracy adjective ("Formally proven correct.",
#: "(verified correct)", "shown to be accurate", "Checked and correct."). "Proved." alone closes a proof and is no label.
_LABEL_VERDICT_WORD = r"(?:correct|accurate|error[- ]free|exact)"
_LABEL_VERDICT = (rf"(?:{_LABEL_ADVERB}(?:proven|proved|shown|demonstrated|found|{_LABEL_WORD})\s+(?:to\s+be\s+)?"
                  rf"(?:(?:fully|entirely|completely|wholly|all)\s+)?{_LABEL_VERDICT_WORD}{_LABEL_BY}?"
                  rf"|{_LABEL_ADVERB}{_LABEL_WORD}\s+(?:and|&)\s+(?:(?:fully|entirely|completely|wholly|all)\s+)?{_LABEL_VERDICT_WORD}"
                  rf"|{_LABEL_VERDICT_WORD}\s+(?:and|&)\s+{_LABEL_ADVERB}{_LABEL_WORD})")
#: A status noun with a checking participle, written as a label: "(accuracy confirmed)", "(facts checked)", "Figures
#: verified.", "(working checked)".
_LABEL_NOUN = (rf"(?:accuracy|correctness|facts?|figures?|dates?|quotations?|quotes?|sources?|citations?|references?|data|numbers?|statistics?"
               rf"|calculations?|arithmetic|working|spellings?)\s+(?:(?:all|fully|now|independently|formally)\s+)?{_LABEL_WORD}{_LABEL_BY}?")
#: A status written as a key and its value: "Verification: passed", "Check status: OK", "Fact-check: complete", "Accuracy:
#: confirmed".
_LABEL_STATUS = (r"(?:verification|checks?|fact[- ]?check(?:ing)?|accuracy(?:\s+check)?|correctness|source[- ]check(?:ing)?)(?:\s+status)?\s*:\s*"
                 r"(?:passed|complete|completed|done|ok|okay|successful|clean|verified|confirmed|checked)\b")
#: The engine, a solver or a checker credited with a verdict, written as a status: "Z3: proved", "(Z3: sat)", "SMT: unsat",
#: "Solver: verified", "Formal check: passed", "Engine verdict: entailed". No agent runs the engine: the verdict it writes is
#: its own claim about a check (the engine's results reach the router signed, never in an agent's text).
_LABEL_ENGINE_STATUS = (r"(?:z3|smt(?:\s+solver)?|(?:the\s+)?(?:solver|verifier|formal\s+(?:check|checker|verification|verifier)|logic\s+engine|engine))"
                        r"(?:\s+(?:result|status|verdict|output))?\s*(?::|=|[—–]|\s-\s)\s*"
                        r"(?:proved|proven|verified|valid|sat|unsat|satisfiable|unsatisfiable|entailed|passed|ok|okay|holds|confirmed|checked)\b")
#: A bracketed status mark ("[OK]", "(OK)", "[PASS]", "[passed]"): a check mark written in letters. Only bracketed: a bare
#: "OK." may open a sentence of an answer.
_LABEL_MARK_BRACKETED = r"(?:\[\s*+(?:ok|okay|pass|passed)\s*+[.!]?\s*+\]|\(\s*+(?:ok|okay|pass|passed)\s*+[.!]?\s*+\))"
#: A check mark written on the text ("✓", "✔", "☑", "✅"): never prose, so wherever it stands outside a quotation it is the
#: writer's mark that something was checked. A cross ("✗") is not one. A run of marks is read as one possessive unit that
#: starts only where a run starts (:data:`_CHECK_RUN`), and the marks are no part of the punctuation around a label
#: (:data:`_LABEL_NON_WORD`), so a long run of marks is read in linear time.
_CHECK_MARK_CHARS = "✓✔☑✅\U0001F5F8️"
_CHECK_MARK = "[✓✔☑✅\U0001F5F8]️?"
_CHECK_RUN = rf"(?<![{_CHECK_MARK_CHARS}])(?:{_CHECK_MARK})++"
_LABEL_TEXT = rf"(?:{_LABEL_STATUS}|{_LABEL_ENGINE_STATUS}|{_LABEL_VERDICT}|{_LABEL_NOUN}|{_LABEL_PHRASE})"
_LABEL = rf"(?:{_CHECK_RUN}(?:\s*{_LABEL_TEXT})?(?:\s*{_CHECK_RUN})?|{_LABEL_TEXT}(?:\s*{_CHECK_RUN})?)"
#: The labels that stand after a bare comma at the end of a sentence (", checked against the sources.", ", verified by
#: Z3.", ", proven correct.", ", accuracy confirmed."): a participle with what it was checked against or by whom, a verdict
#: or a status noun. A bare ", checked." or ", verified." may close a sentence about history ("Inflation was, by 1924,
#: checked."), so it needs "as" (", as verified.").
_LABEL_STRONG = (rf"(?:{_LABEL_VERDICT}|{_LABEL_NOUN}|{_LABEL_ADVERB}{_LABEL_WORD}(?:{_LABEL_BY}{_LABEL_AGAINST}?|{_LABEL_AGAINST}{_LABEL_BY}?)"
                 rf"|{_LABEL_ADVERB}(?:source|spot|machine)[- ]?(?:checked|verified))")
_LABEL_PLACE = r"(?:\s+(?:above|here|below|earlier|throughout|in\s+full))?"
#: Punctuation, brackets, quotation marks and emphasis around a label (never a question mark: "Verified?" asks; never a
#: check mark, which is a label of its own).
_LABEL_NON_WORD = rf"(?:[^\w?{_CHECK_MARK_CHARS}]|_)"
#: The blanks inside the brackets are possessive runs (integration gate 3, parsers): the adjacent ``\s*`` runs around the optional stop
#: split a run of blanks after a bracketed label with no closing bracket in every way, k² steps for each opening bracket (2.5 s at 20,000
#: blanks after "[ok", read for every sentence of every branch by CORE-SELF-001 and by the synthesis reading).
_LABEL_BRACKETED = rf"(?:\[\s*+{_LABEL}\s*+[.!]?\s*+\]|\(\s*+{_LABEL}\s*+[.!]?\s*+\)|{_LABEL_MARK_BRACKETED})"
_LABEL_WHOLE_RE = re.compile(rf"^{_LABEL_NON_WORD}*(?:{_LABEL}{_LABEL_PLACE}|{_LABEL_MARK_BRACKETED}){_LABEL_NON_WORD}*$", re.IGNORECASE)
#: A label in front of the content: bracketed, a check mark ("✔ The constitution ..."), or a capitalised label ("Verified:",
#: "CHECKED —"; a lower-case "checked:" is more likely a name in code) closed by a colon or a dash.
_LABEL_BEFORE_RE = re.compile(
    rf"^{_LABEL_NON_WORD}*?(?:{_LABEL_BRACKETED}|{_CHECK_RUN}(?:\s*{_LABEL_TEXT})?[*_`]*\s*(?::|[—–]|\s-\s)?"
    rf"|(?=(?-i:[A-Z])){_LABEL}[*_`]*\s*(?::|[—–]|\s-\s))[\s*_`]*(?=\S)", re.IGNORECASE)
_LABEL_AFTER_RE = re.compile(
    rf"(?:{_LABEL_BRACKETED}|,\s*as\s+{_LABEL}{_LABEL_PLACE}|,\s*{_LABEL_STRONG}{_LABEL_PLACE}|(?:;|:|[—–]|\s-)\s*(?:as\s+)?{_LABEL}{_LABEL_PLACE}"
    rf"|{_CHECK_RUN}(?:\s*{_LABEL_TEXT})?{_LABEL_PLACE}){_LABEL_NON_WORD}*$",
    re.IGNORECASE)
_LABEL_INSIDE_RE = re.compile(rf"{_LABEL_BRACKETED}|{_CHECK_MARK}", re.IGNORECASE)
#: Cheap pre-filter for the label rule: a sentence with none of these stems (or a check mark) carries no label.
_LABEL_CUE_RE = re.compile(r"verif|check|confirm|validat|certif|corroborat|audit|proof|correct|accura|exact|error|[✓✔☑✅\U0001F5F8]|comprobad|validad|revisad"
                           r"|z3|smt|solver|engine|[\[(]\s*(?:ok|pass)", re.IGNORECASE)
_LABEL_CONTENT_RE = re.compile(r"[^\W_]")


class VerificationLabel(NamedTuple):
    """A verification-status label a sentence carries (:func:`verification_label`): where it stands (``whole``: the
    sentence is nothing but the label; ``before``, ``after`` or ``inside`` its content) and the label as written."""
    position: str
    label: str


#: Cheap pre-filter for the structural rule: a sentence with none of these stems certifies nothing.
_SELF_CUE_RE = re.compile(
    r"check|verif|confirm|validat|corroborat|audit|proof|compar|match|accura|correct|exact|reliab|sound|right|error|faithful|verbatim|trust"
    r"|need|requir|warrant|merit|call|prov|accept|certif|approv|signed|passed|clear|entail|beyond|precis|word\s+for\s+word|letter\s+for\s+letter|without",
    re.IGNORECASE,
)


def strip_json_blocks(text: str) -> tuple[str, int]:
    """Remove pasted JSON blocks (a receipt, a payload) from ``text``.

    A block is removed when it opens with ``{`` or ``[`` at a line start, closes with
    the matching bracket at a line end without crossing a blank line, and either parses
    as JSON or carries a JSON key-value pair. Returns ``(text, number_removed)``.
    """
    removed = 0
    out: list[str] = []
    last = 0
    for start, end in _json_block_spans(text):
        if is_json_block(text[start:end]):
            out.append(text[last:start])
            last = end
            removed += 1
    if not removed:
        return text, 0
    out.append(text[last:])
    return "".join(out), removed


def _json_block_spans(text: str) -> list[tuple[int, int]]:
    """The spans of ``JSON_BLOCK_RE.finditer(text)``, read in linear time (integration gate 2). The pattern's lazy body read
    from every line that opens with a bracket to the next blank line when no bracket closed a line before it, so lines of
    unclosed brackets ('{x' on every line) cost n² steps (2.8 s at 20,000 characters). A block that opens at a bracket closes
    at the first closing bracket after it that ends its line (only blanks after it), unless a line break before a blank line
    comes first, when no block opens there; the closes and the breaks are each found once, so a block is one bisection. The
    blocks are read left to right from the end of the one before, as the pattern's search reads them. The closes are kept as
    offsets and the openers read one at a time, so no match object is kept per line."""
    close_at: list[int] = []
    close_end: list[int] = []
    for c in _JSON_BLOCK_CLOSE_RE.finditer(text):
        close_at.append(c.start())
        close_end.append(c.end())
    if not close_at:
        return []
    breaks = [m.start() for m in _BLANK_LINE_BREAK_RE.finditer(text)]
    spans: list[tuple[int, int]] = []
    resume = 0
    for m in _JSON_BLOCK_START_RE.finditer(text):
        if m.start() < resume:
            continue  # inside the block read before it
        first_body = m.end()  # the opening bracket is the match's last character; the body starts after it
        i = bisect.bisect_left(close_at, first_body)
        if i == len(close_at):
            break  # no bracket closes a line after this opener, nor after any later one
        k = bisect.bisect_left(breaks, first_body)
        if k < len(breaks) and breaks[k] < close_at[i]:
            continue  # a blank line comes before the first close: no block opens here
        spans.append((m.start(), close_end[i]))
        resume = close_end[i]
    return spans


def fence_blocks(text: str) -> list[tuple[int, int, str, str]]:
    """``(start, end, info, body)`` for every paired fence of ``text``: the matches of :data:`FENCE_BLOCK_RE` (``start``,
    ``end``), with the opener's info string (the rest of its line after the fence, blanks before it removed) and the body
    (from the line after the opener to the start of the closing line). Read in linear time (integration gate 2): the
    pattern's lazy body read to the end of the text from every opener that has no closer, n² steps on lines of openers
    ('```a' on every line: 3.3 s at 40,000 characters in :func:`strip_markup`, which is read several times per transfer).
    The fence lines are listed once; an opener takes the first line after it that is nothing but the same fence (blanks
    allowed), and an opener whose line has no line break opens nothing; the fences are read left to right from the end of the
    block before, as the pattern's search reads them. Once an opener of one kind has no closer, no later opener of that kind
    has one, so each kind's closers are read once."""
    lines: list[tuple[int, str, int, int, bool, bool]] = []  # (start, fence, after the fence, line end, has a line break, closes)
    for m in _FENCE_START_RE.finditer(text):
        nl = text.find("\n", m.end())
        end = len(text) if nl < 0 else nl
        lines.append((m.start(), m.group(1), m.end(), end, nl >= 0, not text[m.end():end].strip(" \t")))
    if not lines:
        return []
    closers: dict[str, list[int]] = {"```": [], "~~~": []}
    for i, line in enumerate(lines):
        if line[5]:
            closers[line[1]].append(i)
    cursor = {"```": 0, "~~~": 0}
    blocks: list[tuple[int, int, str, str]] = []
    resume = 0
    for start, fence, after, end, has_break, _closes in lines:
        if start < resume or not has_break:
            continue
        body = end + 1
        found, k = closers[fence], cursor[fence]
        while k < len(found) and lines[found[k]][0] < body:
            k += 1
        cursor[fence] = k
        if k == len(found):
            continue  # no closing line after this opener
        close_start, _f, _a, close_end, _b, _c = lines[found[k]]
        blocks.append((start, close_end, text[after:end].lstrip(" \t"), text[body:close_start]))
        resume = close_end
    return blocks


def _fenced_body(info: str, body: str) -> str:
    """What a paired fence leaves in the text to segment: its body when the fence carries no language (or a text or
    markdown tag) and the body is prose (at least :data:`_MIN_FENCED_PROSE_WORDS` words, two sentence ends, no JSON
    shape): an answer wrapped in a fence is still the answer, as the English parser reads it. Code, a pasted receipt
    (```json ...```) and a short decoration (a footer) are removed whole."""
    info = info.strip().lower()
    if (info in _PROSE_FENCE_TAGS and len(body.split()) >= _MIN_FENCED_PROSE_WORDS and len(_FENCE_SENTENCE_END_RE.findall(body)) >= 2
            and not JSON_KEY_RE.search(body) and not is_json_block(body.strip())):
        return body
    return ""


def _strip_fences(text: str) -> str:
    """``text`` with every paired fence (:func:`fence_blocks`) replaced by what :func:`_fenced_body` leaves of it."""
    blocks = fence_blocks(text)
    if not blocks:
        return text
    out: list[str] = []
    last = 0
    for start, end, info, body in blocks:
        out.append(text[last:start])
        out.append(_fenced_body(info, body))
        last = end
    out.append(text[last:])
    return "".join(out)


def strip_markup(text: str) -> str:
    """Return ``text`` without a byte-order mark, CRLF, heading lines, fenced code
    blocks (fence lines and their body; a fence of prose keeps its body, :func:`_fenced_body`),
    stray fence lines, pasted JSON blocks or emphasis markers. Paragraph breaks (blank lines)
    are preserved. The caller keeps the untouched original for ``original_response``; this is
    only the text to segment."""
    s = text.replace("\r\n", "\n").replace("\r", "\n")
    if s.startswith(BOM):
        s = s[len(BOM):]
    s = s.replace(BOM, "")
    s = HEADING_LINE_RE.sub("", s)
    s = _strip_fences(s)  # the paired fences of FENCE_BLOCK_RE, read in linear time (fence_blocks)
    s = FENCE_LINE_RE.sub("", s)
    s, _removed = strip_json_blocks(s)
    if "___" in s and _BLANK_HOLD not in s:
        # a run of three or more underscores is a blank to fill in ('n = 1.15 ÷ 46.08 = ____ mol'), never an emphasis marker: it is kept
        # as written in the claim text (c1 ch-t14 s3.24, whose blanks were read as emphasis and removed); held apart while the emphasis
        # markers are removed, character for character
        s = _BLANK_RUN_RE.sub(lambda m: _BLANK_HOLD * len(m.group(0)), s)
        return strip_emphasis(s).replace(_BLANK_HOLD, "_")
    s = strip_emphasis(s)  # EMPHASIS_RE.sub(r"\2", s), in linear time
    return s


#: A blank to fill in: three or more underscores. Held as a private-use character (no marker, no word character) while emphasis is removed.
_BLANK_RUN_RE = re.compile(r"_{3,}")
_BLANK_HOLD = "\ue000"


def split_list_items(paragraph: str) -> list[str]:
    """Split a paragraph at newlines that start a list item and drop the markers.

    A paragraph without list markers is returned as a single item; an item that is
    only a marker is dropped. The item texts are the specialist's words, unchanged
    apart from the marker and surrounding whitespace.
    """
    pieces = LIST_LINE_RE.split(paragraph)
    out: list[str] = []
    for piece in pieces:
        stripped = LIST_MARKER_RE.sub("", piece, count=1).strip() if LIST_MARKER_RE.match(piece) else piece.strip()
        if stripped:
            out.append(stripped)
    return out


def truncate_claim_text(text: str, limit: int = MAX_CLAIM_TEXT_CHARS) -> str:
    """Cut ``text`` to the contract limit, marking the cut with ``...``.

    An over-long text has its whitespace runs collapsed to one space before the cut (integration gate 1, overseer handoff
    4): a cut that landed inside a long run of blanks was stripped back to the word before the run, far below the limit, so
    the claim no longer read as cut at the contract limit (the overseer's rule ``contract-cut``: at least the limit less the
    mark, ending in the mark) and a faithful transfer failed its audit (OVS-FID-001 on 'The value is 5 m....'). Collapsing
    changes no word of the claim: every fidelity reading compares a claim with its whitespace normalised. A text within the
    limit is returned as it is."""
    text = text.strip()
    if len(text) <= limit:
        return text
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def is_memory_label(sentence: str) -> bool:
    return bool(MEMORY_LABEL_RE.search(sentence))


def _positive(pattern: "re.Pattern[str]", sentence: str, *, skip_status_words: bool = False) -> bool:
    """True when ``pattern`` matches ``sentence`` at least once outside negation and deontic
    modals ("has not been checked", "should be checked", "must be verified" do not count). With ``skip_status_words``, a match
    written in capitals ("VERIFIED") is a status word, which :func:`self_cert_vocabulary` reads in its frame (integration gate 3:
    "The routine prints VERIFIED when every number matches" is a program's output, not a check of the answer's items)."""
    for m in pattern.finditer(sentence):
        if skip_status_words and m.group(0).isupper():
            continue
        if not _NEGATED_OR_DEONTIC_RE.search(sentence[max(0, m.start() - 60):m.start()]):
            return True
    return False


def _structural_self_report(sentence: str) -> bool:
    """The structural rule: a subject that refers to the answer or its own items (:data:`_SELF_SUBJECT_KINDS_RE`)
    followed directly by a copula and a checking participle or an accuracy adjective. What certifies depends on how
    firmly the subject names the answer:

    * anchored items ("every mileage figure above", "each of the figures given above", "all of the quotations above"):
      any checking participle or accuracy adjective;
    * the answer itself ("my reading", "the whole answer"), every item ("every quoted line"), demonstrative items
      ("these figures", "my quotations") and bare definite items ("the quotations"): a checking participle that closes the
      clause or is made against something, never one credited to another agent ("confirmed by the final stanza", "checked
      by the Registrar General": an argument about evidence); a definite subject only in the present or perfect ("the
      figures were checked" narrates history); an accuracy adjective only when it closes the clause, and only for the
      items an adjective can certify (figures, dates, quotations, statistics, ...; not claims or facts) with no modifier on
      a definite subject ("the census figures are reliable" weighs a source)."""
    sourced = _SELF_SOURCED_RE.finditer(sentence) if _SOURCE_CUE_RE.search(sentence) else ()
    for m in itertools.chain(sourced, _SELF_SUBJECT_KINDS_RE.finditer(sentence)):
        tail = _SELF_PREDICATE_TAIL_RE.match(sentence, m.end())
        if tail is None:
            continue
        kind = m.lastgroup
        after = tail.end()
        if kind == "sourced":
            # items named with their source: anchored in the answer, the answer's own quotations, or a report's items
            strength = _sourced_kind(m.group(0))
            definite = m.group(0).split()[0].lower() not in _NON_DEFINITE_DETERMINERS
            if strength == "anchored":
                return True
            if tail.group("fidelity"):
                if _FIDELITY_END_RE.match(sentence, after):
                    return True
                continue
            if tail.group("check"):
                if (definite and not _SELF_PERFECT_RE.match(sentence, m.end())) or _BY_OTHER_AGENT_RE.match(sentence, after):
                    continue
                if tail.group("check").lower().endswith(("with", "against", "to")) or _CHECK_END_RE.match(sentence, after):
                    return True
                continue
            if strength == "quoted" and _SELF_CLOSING_RE.match(sentence, after):
                return True
            continue
        if tail.group("fidelity"):
            # only the writer reproduces the answer's items: "Every quotation is reproduced exactly as it appears in the extract";
            # a modified definite subject may be another work's items ("the census figures are reproduced exactly ...")
            if kind == "definite" and not _BARE_DEFINITE_RE.fullmatch(m.group(0)):
                continue
            if kind == "anchored" or _FIDELITY_END_RE.match(sentence, after):
                return True
            continue
        if tail.group("check"):
            if kind == "anchored":
                return True
            if kind == "definite" and not _SELF_PERFECT_RE.match(sentence, m.end()):
                continue
            if _BY_OTHER_AGENT_RE.match(sentence, after):
                continue
            if tail.group("check").lower().endswith(("with", "against", "to")) or _CHECK_END_RE.match(sentence, after):
                return True
            continue
        if kind == "anchored":
            return True
        if kind == "definite" and not _BARE_DEFINITE_RE.fullmatch(m.group(0)):
            continue
        if kind != "answer" and not _ACC_ITEM_RE.search(m.group(0)):
            continue
        if _SELF_CLOSING_RE.match(sentence, after):
            return True
    return False


#: A whole-sentence self-assessment of every item of the answer, the words a status mark stands for: "All claims hold.",
#: "Every claim above holds.", "All of the above holds.", "Everything here holds.", "All points stand.", "Each step checks
#: out." Only the sentence as a whole: "All claims hold that ..." and "Hence the above holds for n = 2" argue.
_ALL_HOLD_RE = re.compile(
    r"^\W*(?:(?:all|every|each)\s+(?:of\s+)?(?:(?:the|these|my|our)\s+)?(?:claims?|statements?|points?|figures?|dates?|facts?|steps?|lines?|answers?"
    r"|items?|parts?|calculations?|quotations?)|all\s+of\s+(?:the\s+above|this|it)|everything|the\s+above)"
    r"(?:\s+(?:above|here|below|in\s+(?:this|the|my)\s+(?:answer|paragraph|response)))?"
    r"\s+(?:hold|holds|stand|stands|check\s+out|checks\s+out|(?:is|are)\s+(?:sound|valid|right|fine))\W*$",
    re.IGNORECASE)


# ---- a check of the answer's own items read by its structure (round 9, c2): the verb of checking with the answer's values, marks,
# steps or calculations as its subject or object, the writer or a checking tool as its agent ("All values above were checked by the
# verification engine ...", "All calculations have been verified by the system ...", "All marks above were confirmed against the
# official markscheme.", "All values were verified on a GDC ...", "I recalculated every one of these values myself ...", "This response
# passed every automated check without errors."). Every run is bounded; each pattern is anchored at the sentence's start or at a fixed word.
_CHECK_ITEMS = (r"(?:values?|figures?|calculations?|computations?|marks?|mark\s++allocations?|steps?|answers?|results?|workings?|working|numbers?|sums?"
                r"|totals?|arithmetic|conversions?|substitutions?|units?|quotations?|dates?|data|readings?)")
_CHECK_PARTICIPLE = (r"(?:checked|verified|confirmed|re-?calculated|re-?computed|re-?worked|re-?checked|double[- ]checked|cross[- ]checked|validated|tested"
                     r"|proof-?read|audited)")
#: A checking tool or the writer's own method as the agent or the standard of the check: the answer was checked by or on it.
_CHECK_TOOL_RE = re.compile(r"\b(?:engines?|systems?|solvers?|software|GDCs?|calculators?|spreadsheets?|programs?|automated|automatic|mark\s*+schemes?"
                            r"|(?:official|marking)\s++(?:scheme|criteria|answers?)|by\s++hand|myself|ourselves)\b", re.IGNORECASE)
_CHECK_ANCHOR = r"(?:above|here|below|in\s++(?:this|the|my)\s++(?:answer|response|paragraph|reply|solution|working))"
#: The answer's items as the subject of a checking participle: "All values above were checked ...", "Every step has been verified ...".
_ITEMS_CHECKED_RE = re.compile(
    rf"^[\W_]*+(?P<det>(?:all|every|each)(?:\s++one)?(?:\s++of)?(?:\s++(?:the|these|those|my|our))?|these|those|my|our)\s++(?:[\w-]+\s++){{0,2}}?"
    rf"{_CHECK_ITEMS}(?P<anchor>\s++{_CHECK_ANCHOR})?\s++(?:were|was|have\s++been|has\s++been|had\s++been|are|is)\s++"
    rf"(?:(?:all|each|both|also|now|fully|independently|carefully|individually|already|thoroughly|duly)\s++){{0,3}}{_CHECK_PARTICIPLE}\b",
    re.IGNORECASE)
#: The writer re-working its own items: "I recalculated every one of these values myself", "I recalculated these values by hand", "I proofread
#: my answer", "I have reviewed all the figures above" (round 9 second pass: reviewing and proofreading are checks of the writer's own items too).
_WRITER_REWORKED_RE = re.compile(
    rf"\b(?:I|we)\s++(?:have\s++|['’]ve\s++|had\s++)?(?:(?:also|now|personally|carefully|independently|then)\s++){{0,2}}"
    rf"(?:re-?calculated|re-?computed|re-?worked|re-?did|re-?checked|double[- ]checked|cross[- ]checked|reviewed|proof-?read|re-?read)\s++"
    rf"(?:(?:all|every|each)(?:\s++one)?(?:\s++of)?\s++(?:the\s++)?|these\s++|those\s++|my\s++|our\s++|them\b|it\b)(?:[\w-]+\s++){{0,2}}?(?:{_CHECK_ITEMS}\b|them\b|it\b)?",
    re.IGNORECASE)
#: The answer passing checks: "This response passed every automated check without errors."
_ANSWER_PASSED_RE = re.compile(
    r"\b(?:this|the|my|our)\s++(?:response|answer|paragraph|reply|essay|text|work|solution|working|report)\s++(?:has\s++|have\s++)?pass(?:ed|es)\s++"
    r"(?:every|all|each|the|its)\s++(?:[\w-]+\s++){0,2}?(?:checks?|tests?|verifications?|validations?|reviews?)\b", re.IGNORECASE)
#: The writer vouching for its own answer in the first person (round 9 second pass, the class of c2 adversarial-live bug 17): "I reviewed the
#: whole text and confirm there are no errors.", "We confirm that every figure above is correct." The verb 'confirm' after 'I', 'we' or, in a
#: sentence whose subject is the writer, after 'and' (:func:`_narrated_check` requires the pronoun before it), with a clause that says the
#: answer, its items or everything holds no error or is correct. Anchored at the pronoun or at 'and'; every run bounded.
_ANSWER_WHOLE = r"(?:the|this|my|our)\s++(?:whole\s++|entire\s++)?(?:answer|response|text|essay|paragraph|working|solution|report|article|reply)"
_FIRST_PERSON_CONFIRM_RE = re.compile(
    rf"\b(?P<who>I|we|and)\s++(?:(?:can|hereby|also|now|fully)\s++){{0,2}}confirm(?:ed|s)?\s++(?:that\s++)?"
    rf"(?:there\s++(?:are|is|were|was)\s++no\s++(?:(?:further|remaining|other|more)\s++)?(?:errors?|mistakes?|slips?)\b"
    rf"|(?:everything|it\s++all|all\s++of\s++(?:it|them|these)|all|they\s++all|{_ANSWER_WHOLE}"
    rf"|(?:all|every|each)\s++(?:one\s++of\s++)?(?:the\s++|these\s++|my\s++|our\s++)?{_CHECK_ITEMS})\s++(?:(?:above|here)\s++)?"
    r"(?:(?:is|are|was|were)\s++(?:all\s++|now\s++|fully\s++)?(?:correct|accurate|right|exact|error-free)\b|contains?\s++no\s++(?:errors?|mistakes?)\b))",
    re.IGNORECASE)
#: The same in Spanish (Language B answers): a first-person verb of checking with the answer or its items as object ("Revisé todo el texto",
#: "He comprobado los cálculos", "Verifiqué cada dato con la tabla", "Lo he revisado todo"), or with a clause that says they hold no error
#: ("Comprobé que todas las cifras coinciden con la tarea"), and a first-person 'confirmo que' with such a clause ("Confirmo que el texto no
#: contiene errores"). Only accented preterite forms are read ('revisé', never the English 'revise'); a possessor other than the answer ('las
#: cifras del ayuntamiento') makes the object another party's. Anchored at the verb; every run bounded.
_ES_CHECK_VERB = (r"(?:revis[ée]|comprob[ée]|verifiqu[ée]|repas[ée]|recalcul[ée]|cotej[ée]|chequ[ée]{1,2}|revisamos|comprobamos|verificamos|repasamos|recalculamos"
                  r"|(?:he|hemos)\s++(?:(?:ya|tambi[ée]n|cuidadosamente|personalmente)\s++)?(?:revisado|comprobado|verificado|repasado|recalculado|cotejado|chequeado"
                  r"|vuelto\s++a\s++(?:calcular|comprobar|revisar|verificar|leer)))")
_ES_OWN_ITEMS = (r"(?:texto|respuesta|redacci[óo]n|art[íi]culo|carta|ensayo|trabajo|c[áa]lculos?|cifras?|datos?|resultados?|valores?|operaciones?"
                 r"|ortograf[íi]a|gram[áa]tica|citas?|fechas?|n[úu]meros?|porcentajes?)")
_ES_OWN_DET = (r"(?:tod[oa]s?\s++(?:l[oa]s?\s++|el\s++|est[oa]s?\s++|mis?\s++)?|cada\s++(?:un[oa]\s++de\s++(?:l[oa]s|est[oa]s|mis)\s++)?"
               r"|(?:el|la|los|las|este|esta|estos|estas|mi|mis)\s++)")
_ES_NO_ERROR = (rf"(?:no\s++hay\s++(?:ning[úu]n\s++)?(?:errores?|fallos?)|(?:todo|{_ES_OWN_DET}{_ES_OWN_ITEMS})\s++(?:no\s++(?:contiene|tiene|presenta)n?\s++"
                rf"(?:ning[úu]n\s++)?(?:errores?|fallos?)|(?:es|son|est[áa]n?)\s++(?:tod[oa]s?\s++)?(?:correct[oa]s?|exact[oa]s?|bien)|coincide[n]?|cuadra[n]?))")
_ES_NARRATED_CHECK_RE = re.compile(
    rf"\b{_ES_CHECK_VERB}\s++(?:(?:de\s++nuevo|otra\s++vez|cuidadosamente|a\s++mano|yo\s++mism[oa])\s++)?"
    rf"(?:que\s++{_ES_NO_ERROR}|todo\b(?!\s++(?:lo\s++que|el\s++(?:barrio|mundo|pueblo|d[íi]a|a[ñn]o)))|{_ES_OWN_DET}{_ES_OWN_ITEMS}\b(?!\s++(?:de|del)\s++(?!(?:esta|este|mi|arriba)\b)))"
    rf"|\bconfirm(?:o|amos)\s++que\s++{_ES_NO_ERROR}",
    re.IGNORECASE)
#: A negation right before the verb ("No he revisado los cálculos", "nunca comprobé las cifras"): a disclaimer, never a self-report.
_ES_NEGATION_BEFORE_RE = re.compile(r"\b(?:no|nunca|jam[áa]s|todav[íi]a\s++no|a[úu]n\s++no)\s++(?:(?:lo|la|los|las|me|nos)\s++)?$", re.IGNORECASE)
#: Cheap pre-filter of :func:`_narrated_check`.
_NARRATED_CUE_RE = re.compile(r"confirm|revis|comprob|verifiqu|verificad|verificamos|repas|recalcul|cotej|chequ", re.IGNORECASE)


def _narrated_check(sentence: str) -> bool:
    """True when ``sentence`` (quotations masked) narrates the writer's own check of its answer and vouches for it, in English or in Spanish
    (:data:`_FIRST_PERSON_CONFIRM_RE`, :data:`_ES_NARRATED_CHECK_RE`); a 'confirm' after 'and' counts only when 'I' or 'we' stands before it
    in the sentence, and a negation or a deontic modal before the verb makes the sentence a disclaimer."""
    if not _NARRATED_CUE_RE.search(sentence):
        return False
    for rx in (_FIRST_PERSON_CONFIRM_RE, _ES_NARRATED_CHECK_RE):
        for m in rx.finditer(sentence):
            before = sentence[max(0, m.start() - 40):m.start()]
            if _NEGATED_OR_DEONTIC_RE.search(before) or _ES_NEGATION_BEFORE_RE.search(before):
                continue
            if rx is _FIRST_PERSON_CONFIRM_RE and m.group("who").lower() == "and" and not re.search(r"\bI\b|\b[Ww]e\b", sentence[:m.start()]):
                continue  # 'Check your work and confirm there are no errors': an instruction to the reader, not the writer's own check
            return True
    return False


def _structural_check_report(sentence: str) -> bool:
    """True when ``sentence`` reports a check of the answer's own items by its structure (the comment above): the items as the subject
    of a checking participle, anchored in the answer ("above", "in this answer"), named by the writer's own determiner ("these", "my") or
    checked by or on a tool ("by the verification engine", "on a GDC", "against the official markscheme"); the writer re-working its
    items; the answer passing checks. A check under negation or a deontic modal is a disclaimer ("the values have not been checked"), and
    items checked by another party with no anchor ("All ballots were checked by the commission") are history. Read with quotations
    masked: a colleague's self-report quoted is the colleague's."""
    sentence = mask_quotations(sentence)
    m = _ITEMS_CHECKED_RE.match(sentence)
    if m is not None and not _NEGATED_OR_DEONTIC_RE.search(sentence[max(0, m.end() - 80):m.end()].rsplit(" ", 1)[0] + " "):
        det = m.group("det").split()[0].lower()
        if m.group("anchor") or _CHECK_TOOL_RE.search(sentence) or re.search(rf"\s{_CHECK_ANCHOR}\b", sentence, re.IGNORECASE):
            return True
        if det in ("these", "those", "my", "our") and _CHECK_END_RE.match(sentence, m.end()):
            return True  # 'These values were checked.', 'My figures have been verified against the table'; not '... confirmed by later studies'
    if _positive(_WRITER_REWORKED_RE, sentence) or _positive(_ANSWER_PASSED_RE, sentence):
        return True
    return _narrated_check(sentence)  # the writer vouching for its own check, in English or in Spanish (round 9 second pass)


@functools.lru_cache(maxsize=8192)
def _self_certification(sentence: str) -> bool:
    if self_cert_vocabulary(sentence) is not None or is_json_shaped(sentence) or _ALL_HOLD_RE.match(sentence):
        return True
    if _FIRST_PERSON_CHECK_RE.search(sentence) or _SELF_LEAD_RE.match(sentence):
        return True
    if _LABEL_CUE_RE.search(sentence) and _LABEL_WHOLE_RE.match(sentence):
        return True  # nothing but a verification label ("Verified.", "(checked)", "Verification: passed.")
    cue = _SELF_CUE_RE.search(sentence) is not None
    if cue and (_positive(_NOTHING_NEEDS_CHECK_RE, sentence)
                or (_SELF_SUBJECT_KINDS_RE.search(sentence) is not None and _positive(_NO_FURTHER_CHECK_RE, sentence))):
        return True
    # compliance with the request and word-count lines: decided before the dated-item guard, since "the 1633 spelling of the
    # supplied text" and "the 300-word limit" carry numbers that date nothing
    if len(sentence) <= 400 and (_WORD_COUNT_RE.match(sentence) or _COMPLIANCE_RE.match(sentence) or _quoted_words_fidelity(sentence)):
        return True
    if _DATED_ITEM_RE.search(sentence):
        return False
    if len(sentence) <= 600 and _structural_check_report(sentence):
        return True
    if _SELF_SUBJECT_RE.search(sentence) or _SELF_ACCURACY_RE.search(sentence):
        if _positive(_SELF_ACCURACY_RE, sentence) or _positive(_SELF_PREDICATE_RE, sentence, skip_status_words=True):
            return True
        if _INFRASTRUCTURE_RE.search(sentence) and _positive(_INFRASTRUCTURE_VERB_RE, sentence):
            return True
    if not cue:
        return False
    if _structural_self_report(sentence):
        return True
    subjects = [m.lastgroup for m in _SELF_SUBJECT_KINDS_RE.finditer(sentence)]
    if subjects and _positive(_STRONG_MATCH_RE, sentence):
        return True
    return bool(_positive(_INFRA_AGENT_RE, sentence) and (_INFRA_OBJECT_RE.search(sentence) or any(k != "definite" for k in subjects)))


def is_self_certification(sentence: str) -> bool:
    """True when the sentence certifies the answer's own checking, on every branch the same way:

    * verification-status vocabulary (:func:`self_cert_vocabulary`: :data:`SELF_CERT_RE` anywhere, and the words that are also
      ordinary content of the subjects, "no findings", "checked and confirmed", "cross-checked", "approved by the overseer", a capital
      status word that is no label, only in a frame: the answer or its items in the same clause, the writer's own check, a finding
      code or a receipt field, or a sentence of nothing but the words; integration gate 3) or the shape of a JSON receipt or payload;
    * the writer narrating its own check ("I have checked each of these dates", "I verified each figure", "we have
      confirmed"), or a certifying lead ("As verified, ...", "As checked above, ...", "As the hub has confirmed, ...";
      "As confirmed by Engels, ..." cites a source and is not one);
    * nothing left to check: a subject that refers to the answer or its items with "need(s) no further checking",
      "require no verification", "need not be checked", or "nothing in this answer needs checking", "none of the figures
      above needs checking";
    * the semantic rule, with no dated item: the sentence speaks of the answer itself ("this paragraph", "the above",
      "the argument above"), of every item in it ("every figure and date", "all of these figures") or of its items
      located in it ("the figures here", "every quotation above") with a positive checking predicate anywhere (checked,
      verified, appears verbatim, can be relied upon, no errors were found) or an accuracy adjective right after that
      subject, or says that the verification infrastructure (Z3, the engine, the solver, the hub) passed it;
    * the structural rule (:func:`_structural_self_report`), decided by the clause's shape rather than by listed phrases: a
      subject that refers to the answer's own items, a determiner ("every", "each of the", "all of the", "these", "my",
      "the") with up to two modifiers before an item noun ("every mileage figure", "each of the mileage figures given
      above", "these quotations", "every quoted line above"), or the answer itself ("my reading", "the whole answer"),
      followed directly by a copula and a checking participle ("has been verified", "have been formally verified") or an
      accuracy or reliability adjective ("are exact", "are accurate", "are reliable"), with the limits that keep
      arguments arguments: a check credited to another agent ("my reading is confirmed by the final stanza") or one that
      goes on to argue ("verified in later scholarship") is not a self-report, an adjective must close the clause unless
      the items are anchored in the answer ("here", "above", "in this answer"), and a subject that mentions only items
      in general ("every figure in the sculpture is exact") needs a checking verb;
    * items named with the source they were taken from ("each quotation of the History specialist above", "my
      quotations of both texts", "the quotations from the History report", "every figure taken from the History
      specialist") with a checking participle, an accuracy adjective (anchored items, quotations, or items taken by a
      quoting participle) or a reproduction-fidelity predicate ("has been reproduced exactly", "are quoted verbatim");
      a report's figures with only an adjective ("the figures of the History report are accurate") may be the writer
      vouching for a source and are not one;
    * compliance with the request, decided before the dated-item guard: a sentence that opens on the answer, its
      quotations or the request's items and says nothing but that the answer satisfies the request ("The paragraph is
      under the word limit.", "This paragraph stays within the 300-word limit and answers every part of the
      question.", "The answer meets every constraint in the request.", "Both request items are addressed above.",
      "This response complies with the router's instructions.", "All quotations follow the 1633 spelling of the
      supplied text."), and a word-count line ("Word count: 258.", "258 words.");
    * items matched word for word or checked against "the supplied" text ("The quotations were matched word for word
      against the supplied extract");
    * the infrastructure (Z3, the engine, solver, verifier, checker, hub, channel, router, translator, Overseer,
      combinator) as the agent of a certifying verb with the answer or its items as what it passed ("The router has
      confirmed that every item is addressed", "The Overseer signed off on this answer");
    * a sentence that is nothing but a verification label ("Verified.", "(checked)", "Fact-checked and confirmed.",
      "Verification: passed."; :func:`verification_label`, position ``whole``). A label attached to content ("Verified:
      The constitution was adopted in August 1919.") is not a self-certification of the sentence: the content stays a
      claim, and the hub names the label on its own (CORE-SELF-001, INT-LEDGER-029).

    Only a POSITIVE predicate counts: a check under negation or a deontic modal ("The dates in this paragraph have not
    been checked", "... are from memory and should be checked before they are cited", "must be verified") is a
    disclaimer, never a self-certification. Answers are cached per sentence (pure function of the text)."""
    return _self_certification(sentence) if len(sentence) <= _CACHE_MAX_CHARS else _self_certification.__wrapped__(sentence)


@functools.lru_cache(maxsize=8192)
def _verification_label(sentence: str) -> Optional[VerificationLabel]:
    if not _LABEL_CUE_RE.search(sentence):
        return None
    masked = mask_quotations(sentence.strip())  # a quoted label is the quoted text's, not the writer's
    if not _LABEL_CUE_RE.search(masked):
        return None
    if _LABEL_WHOLE_RE.match(masked):
        return VerificationLabel("whole", masked.strip()[:200])
    m = _LABEL_BEFORE_RE.match(masked)
    if m is not None and _LABEL_CONTENT_RE.search(masked, m.end()):
        return VerificationLabel("before", masked[:m.end()].strip()[:200])
    m = _LABEL_AFTER_RE.search(masked)
    if m is not None and _LABEL_CONTENT_RE.search(masked[:m.start()]):
        return VerificationLabel("after", masked[m.start():].strip()[:200])
    m = _LABEL_INSIDE_RE.search(masked)
    if m is not None:
        return VerificationLabel("inside", m.group(0).strip()[:200])
    return None


# ---- the combinator's own product as the answer itself (:func:`is_synthesis_self_certification`): where the combinator
# is the writer, "the synthesis", "this synthesis", "the combined answer" and "the synthesized claims" are what "this
# answer" and "the figures here" are in a specialist's text. On a specialist's branch the same words are content ("the
# synthesis of ammonia", "This synthesis was confirmed by NMR"), so only the hub's reading of a synthesis reads them.
_SYNTH_PRODUCT = (r"(?:synthesis|syntheses|combination|(?:combined|synthesi[sz]ed|merged)\s+(?:answer|account|response|text|paragraph|summary|version"
                  r"|report|reply))")
#: The combinator's product or its claims as a subject: "the synthesis", "this synthesis", "the combined answer", "the whole
#: synthesis above", "the synthesized claims", "every synthesized claim", "all claims in this synthesis". A product followed
#: by "of", "between" or "from" ("the synthesis of ammonia") names something else.
_SYNTH_SUBJECT_RE = re.compile(
    rf"\b(?:(?:this|that|my|our|its|the)(?:\s+(?:whole|entire|final|present|above|full|resulting))?\s+{_SYNTH_PRODUCT}(?:\s+(?:above|here|below))?"
    rf"(?!\s+(?:of|between|from)\b)"
    rf"|(?:{_SELF_UNIVERSAL_DET}\s+|(?:the|these|those|its|our|my)\s+)?(?:synthesi[sz]ed|combined|merged)\s+{_SELF_ITEM_LIST}"
    rf"|(?:{_SELF_UNIVERSAL_DET}\s+|(?:the|these|those)\s+)?{_SELF_ITEM_LIST}\s+(?:in|of|from)\s+(?:this|the|my|our)\s+(?:(?:whole|entire|final)\s+)?"
    rf"{_SYNTH_PRODUCT})\b",
    re.IGNORECASE,
)
#: Cheap pre-filter for the synthesis reading: a sentence that names no combined product is read by the specialists' rules only.
_SYNTH_CUE_RE = re.compile(r"synthes|combin|merged", re.IGNORECASE)
#: What a check credited to someone other than the writer (the combinator) or the infrastructure looks like in the rest of
#: the clause: "The synthesis was checked by the History specialist" credits another agent and is no self-report.
_SYNTH_BY_OTHER_RE = re.compile(rf"\bby\s+(?!(?:me|myself|us|ourselves|the\s+(?:writer|author)|this\s+combinator|{_INFRASTRUCTURE})\b)", re.IGNORECASE)
_SYNTH_CLAUSE_END_RE = re.compile(r"[.;!?]|,\s+(?:but|while|whereas|although|though|yet)\b")
#: An accuracy adjective's complement before the clause closes: "faithful to the sources", "accurate to every source claim",
#: "correct in every detail".
_SYNTH_COMPLEMENT_RE = re.compile(
    r"\s+(?:(?:to|with|against)\s+(?:(?:the|its|all(?:\s+(?:the|its))?|every|each(?:\s+of\s+the)?|both)\s+)?(?:[\w'’-]+\s+){0,2}?"
    r"(?:sources?|source\s+claims?|reports?|specialists?['’]?\s*(?:answers?|reports?|claims?)?|originals?|answers?|claims?|texts?|evidence)"
    r"|in\s+(?:every|each|all(?:\s+its)?)\s+(?:details?|respects?|particulars?|points?|claims?))\b",
    re.IGNORECASE,
)
#: A combined product said to reproduce its sources faithfully, to match them, or to have passed a check: "accurately
#: reflects the sources", "faithfully restates every source claim", "matches the specialists' reports", "is consistent with
#: the sources", "passed every check", "has passed the hub's verification".
_SYNTH_FIDELITY_VERB_RE = re.compile(
    r"\s+(?:(?:has|have)\s+(?:(?:now|already|also)\s+)?)?(?:"
    r"(?:accurately|faithfully|correctly|exactly|precisely|fully|truly)\s+(?:reflect|represent|reproduce|restate|capture|preserve|convey|report|summari[sz]e"
    r"|combine|render|state|record)(?:s|d|ed)?\b"
    r"|(?:match(?:es|ed)?|agree[sd]?\s+with|(?:is|are|was|were)\s+(?:fully\s+|entirely\s+|wholly\s+)?(?:consistent\s+with|faithful\s+to|true\s+to)"
    r"|correspond(?:s|ed)?\s+to|conform(?:s|ed)?\s+to)\s+(?:(?:the|its|all(?:\s+(?:the|its))?|every|each(?:\s+of\s+the)?|both)\s+)?(?:[\w'’-]+\s+){0,2}?"
    r"(?:sources?|source\s+claims?|reports?|specialists?['’]?\s*(?:answers?|reports?|claims?)?|originals?)\b"
    r"|pass(?:es|ed)\s+(?:(?:all|every|each|the)\s+)?(?:(?:of\s+)?(?:the\s+)?)?(?:[\w'’-]+['’]s\s+)?(?:(?:formal|verification|integrity|hub|engine|z3"
    r"|ledger|automatic|automated)\s+)?(?:checks?|verification|validation|review|audit|tests?)\b"
    r")",
    re.IGNORECASE,
)
#: Nothing in the combined product to check: "Nothing in this synthesis needs checking", "No claim of the synthesis requires
#: further verification".
_SYNTH_NOTHING_RE = re.compile(
    rf"\b(?:nothing|no\s+(?:claim|figure|date|statement|part)|none\s+of\s+the\s+(?:claims|figures|dates|statements))\s+(?:in|of)\s+(?:this|the)\s+"
    rf"{_SYNTH_PRODUCT}\s+(?:needs?|requires?|calls?\s+for|merits?|warrants?)\s+(?:any\s+|further\s+|more\s+)?"
    r"(?:check(?:ing)?|verification|correction|to\s+be\s+(?:re-?)?(?:checked|verified))\b",
    re.IGNORECASE,
)


#: No error found in the combined product: "No errors were found in this synthesis.", "No mistakes have been detected in the
#: combined answer.", "This synthesis contains no errors." (the specialists' reading names the same words about "this answer").
_SYNTH_NO_ERRORS_RE = re.compile(
    rf"\bno\s+(?:errors?|mistakes?|inaccuracies|problems?|issues?|faults?|discrepancies)\s+(?:(?:were|was|have\s+been|has\s+been|could\s+be|can\s+be)\s+)?"
    rf"(?:found|detected|identified|spotted)\s+(?:in|within|across)\s+(?:(?:this|the|my|our)\s+)?(?:(?:whole|entire|final|present)\s+)?{_SYNTH_PRODUCT}\b"
    rf"|\b(?:this|the|my|our)\s+(?:(?:whole|entire|final|present)\s+)?{_SYNTH_PRODUCT}\s+(?:contains|has|holds|shows)\s+no\s+(?:errors?|mistakes?|inaccuracies|faults?)\b",
    re.IGNORECASE,
)
#: A proof verdict a combinator writes on a claim, bracketed: "(proven)", "(proved)", "[proven]", "(formally proven)", "(proof
#: complete)". A specialist's "proved" closes a proof and is content, so only the hub's reading of a synthesis reads it
#: (:func:`synthesis_label`).
_SYNTH_PROOF_LABEL_RE = re.compile(r"[\[(]\s*(?:formally\s+|fully\s+)?(?:proven|proved|proof\s+(?:complete|completed|checked|verified))\s*+[.!]?\s*+[\])]",
                                   re.IGNORECASE)
# ---- the combinator's own verdict on what it wrote (integration gate 2, finding 7), read on a synthesis only (:func:`synthesis_label`,
# :func:`is_synthesis_self_certification`): the engine's, the hub's and the Overseer's vocabulary written as a label ("(sat)", "(signed
# engine result)", "(signature valid)", "(logic check passed)", "(entailment holds)", "(the hub accepted this)", "Overseer verdict:
# pass."), a leading verdict ("Correct: ...", "Fact: ..."), a closing self-assessment ("...; this is fully reliable.", "..., which is
# beyond doubt.") and the answer itself as the subject of a verdict ("The answer is correct.", "This answer is complete and correct.",
# "This has been verified."). No agent can write a signed result or an Overseer verdict, and the combined answer is the answer, so each is
# a self-report (INT-LEDGER-029, advisory); on a specialist's branch the same words may be content ("the formula is satisfiable (sat)",
# "The answer is correct" about the student's working), so the specialists' reading keeps them out. A negated or failed verdict ("(not
# sat)", "(signature invalid)", "(logic check failed)") and a check credited to another agent are no label.
_SYNTH_VERDICT_TERM = (
    r"(?:sat|unsat|satisfiable|unsatisfiable|entailed|entailment\s+(?:holds|confirmed|proved|proven|verified)|proved|proven"
    r"|signed(?:\s+(?:engine\s+|hub\s+)?(?:result|receipt|verdict|check))?|(?:engine\s+|hub\s+)?signature\s+(?:valid|verified|ok|okay|checks\s+out)"
    r"|valid\s+signature|receipt\s*:\s*(?:accepted|ok|okay|verified|passed|clean)"
    r"|(?:accepted|approved|passed|cleared|verified|confirmed)\s+by\s+(?:the\s+)?(?:hub|engine|overseer|router|channel|ledger|z3|solver|verifier)"
    r"|(?:the\s+)?(?:hub|engine|overseer|router|channel|ledger|z3|solver|verifier)\s+(?:has\s+)?(?:accepted|approved|passed|cleared|verified|confirmed)"
    r"(?:\s+(?:this|it|the\s+claim))?"
    r"|(?:logic|formal|engine|z3|integrity|hub|ledger|signature)\s+checks?\s*(?::\s*)?(?:passed|ok|okay|clean|complete|completed)"
    r"|overseer(?:['’]s)?\s++(?:(?:verdict|status|audit)\s*+)?(?::\s*+)?(?:pass|passed|approved|ok|okay|clean)|audit(?:ed)?\s*+(?::\s*+)?(?:passed|clean|ok))"
)
#: The blanks around the optional stop are possessive runs (integration gate 2): adjacent ``\s*`` runs split a run of blanks after a label
#: with no closing bracket in every way, k² steps for each opening bracket. Integration gate 3 (parsers) read the runs inside the term the
#: same way: "overseer", its optional key and its optional colon had three adjacent runs (k³ steps: 8.8 s at 1,000 blanks after
#: "(overseer"), "audit" two.
_SYNTH_VERDICT_LABEL_RE = re.compile(rf"[\[(]\s*{_SYNTH_VERDICT_TERM}\s*+[.!]?\s*+[\])]", re.IGNORECASE)
#: A status key in the engine's, the hub's or the Overseer's name written as a sentence of its own or around content: "Overseer verdict:
#: pass.", "Engine status: entailed", "Hub: accepted". A negated or failed value ("Overseer verdict: fail") is no label.
#: Integration gate 3 adds the keys of a quality check ("QA: pass.", "Quality check: passed", "Review: approved", "Validation: OK", "Fact-check:
#: confirmed", "Accuracy check: passed").
_SYNTH_STATUS_KEY_RE = re.compile(
    r"\b(?:overseer|engine|hub|router|channel|ledger|audit|logic\s+check|formal\s+check|signature|q\.?a\.?|quality\s+(?:check|control|assurance)|review"
    r"|validation|fact[- ]?check|accuracy\s+check)(?:['’]s)?(?:\s+(?:verdict|status|result|check|decision))?"
    r"\s*+:\s*+(?:pass|passed|ok|okay|accepted|approved|entailed|sat|unsat|verified|valid|signed|clean|confirmed)\b(?![-'’])", re.IGNORECASE)
#: A leading verdict on the claim: "Correct: ...", "Fact: ...", "True: ...".
_SYNTH_LEAD_VERDICT_RE = re.compile(r"^[\s*_`>-]*(?:correct|fact|true|accurate|verified\s+fact|confirmed\s+fact)[*_`]*\s*(?::|[—–]|\s-\s)\s*(?=\S)", re.IGNORECASE)
#: A self-assessment that closes the claim: "...; this is fully reliable.", "..., which is beyond doubt.", "... — this is certain.".
#: Integration gate 3 adds the intensifiers ("...; this is definitely correct.", "..., which is certainly true."); the blanks after the verdict
#: are possessive runs, so a long blank run before a character that defeats the match is read once.
_SYNTH_INTENSIFIER = r"(?:definitely|certainly|undoubtedly|unquestionably|surely|clearly|indeed|positively)"
_SYNTH_SELF_ASSESS_RE = re.compile(
    r"(?:[;,:—–]|\s-)\s*(?:this|it|which|that|all\s+(?:of\s+)?this)\s+(?:is|was|has\s+been|remains|stands)\s+"
    rf"(?:{_SYNTH_INTENSIFIER}\s+true|(?:(?:fully|entirely|completely|absolutely|wholly|totally|perfectly|100%|{_SYNTH_INTENSIFIER})\s+)?"
    r"(?:reliable|certain|beyond\s+(?:any\s+|all\s+|reasonable\s+)?(?:doubt|question|dispute)|indisputable|undisputed|unquestionable|incontestable"
    r"|(?:an?\s+)?(?:established|verified|confirmed|proven)\s+fact|correct|accurate|verified|confirmed|checked))\s*+[.!]?\s*+$",
    re.IGNORECASE)
#: The answer, the combined answer or 'this'/'it' as the subject of a verdict that is the whole sentence: "The answer is correct.", "This
#: answer is complete and correct.", "This has been verified.", "It is fully reliable." ("This answer is correct." the specialists'
#: reading names too.) A verdict under negation, credited to another agent or followed by more of the sentence is no self-report.
_SYNTH_ANSWER_VERDICT_RE = re.compile(
    r"^[\W_]*(?:(?:the|this|my|our)\s+(?:(?:whole|entire|final|full|complete|combined)\s+)?(?:answer|response)(?:\s+(?:above|here|below))?|this|it"
    r"|all\s+of\s+(?:this|it))\s+(?:is|was|has\s+been|have\s+been|remains)\s+"
    r"(?:(?:now|all|fully|completely|entirely|thoroughly|independently|formally|carefully|absolutely|100%)\s+)*"
    r"(?:(?:complete|comprehensive|full)\s+and\s+(?:correct|accurate)|(?:correct|accurate)\s+and\s+(?:complete|comprehensive)|correct|accurate|verified"
    r"|checked|confirmed|validated|reliable|error[- ]free|beyond\s+(?:any\s+|all\s+)?(?:doubt|question))[\W_]*$", re.IGNORECASE)
#: A demonstrative or the claim itself with an intensified verdict, the whole sentence (integration gate 3): "This is definitely correct.",
#: "This claim is certainly true.", "That is undoubtedly accurate." A verdict without an intensifier is :data:`_SYNTH_ANSWER_VERDICT_RE`'s.
_SYNTH_INTENSE_VERDICT_RE = re.compile(
    r"^[\W_]*(?:this|that|it|all\s+of\s+(?:this|it)|(?:this|the)\s+(?:claim|statement|point|fact|figure|date|answer|synthesis))\s+(?:is|was|remains)\s+"
    rf"(?:(?:absolutely|completely|entirely|totally|wholly|perfectly|100%)\s+)?{_SYNTH_INTENSIFIER}\s+(?:(?:absolutely|completely|entirely|totally)\s+)?"
    r"(?:correct|accurate|true|right|reliable|verified|confirmed|established)[\W_]*$", re.IGNORECASE)
#: The verification infrastructure and the checks named as what confirmed or passed the claim (integration gate 3): a clause closing the
#: claim after a separator ("..., which the engine confirms.", "..., as Z3 confirms.", "..., as the overseer approved.", "..., a fact the
#: checker confirmed.", and, for the names that are only the system's, "...; the hub has verified it." with no connective), every check said to have passed ("All checks passed.", "Every check passed.",
#: "...; this passed all checks."), or a signed result claimed for it ("This claim carries a signed engine result."). Read on a synthesis
#: only. The names that are also ordinary words of the subjects (the overseer, the translator, the checker, the verifier, Z3) count after
#: "which", "this", "that" or "and" only with a verb of verification ("The planters introduced new punishments, which the overseer
#: approved." is History); a verb under negation, a source credited ("as the treaty's text confirms") or a clause that goes on ("..., which
#: the overseer approved in 1820") is no self-report.
_SYNTH_SYSTEM_NAME = (r"(?:the\s+)?(?:(?:verification|logic|formal|z3|smt)\s+)?(?:engine|solver)|the\s+(?:hub|ledger|channel|router)|(?:the\s+)?formal\s+checks?"
                      r"|(?:the\s+)?(?:automated|automatic|integrity|verification)\s+checks?")
_SYNTH_WORD_NAME = r"z3|the\s+(?:checker|verifier|overseer|translator)"
_SYNTH_ANY_VERB = (r"(?:confirm(?:s|ed)?|verif(?:y|ies|ied)|prov(?:e|es|ed|en)|approv(?:e|es|ed)|certif(?:y|ies|ied)|validat(?:e|es|ed)|accept(?:s|ed)?"
                   r"|entail(?:s|ed)?|pass(?:es|ed)?|clear(?:s|ed)|signed\s+off(?:\s+on)?)")
_SYNTH_CHECK_VERB = r"(?:confirm(?:s|ed)?|verif(?:y|ies|ied)|prov(?:e|es|ed|en)|certif(?:y|ies|ied)|validat(?:e|es|ed)|entail(?:s|ed)?)"
_SYNTH_VERB_TAIL = r"(?:\s++(?:it|this|that|the\s+claim|so))?\s*+[.!]?[\s\"'”’)\]]*+$"
_SYNTH_AUX = r"(?:(?:has|have|had)\s++)?(?:(?:also|now|already|independently|formally|fully)\s++)?"
_SYNTH_INFRA_CREDIT_RE = re.compile(
    rf"(?:(?:[,;:—–]|\s-)\s*+(?:(?:as|a\s+fact(?:\s+that)?|something(?:\s+that)?)\s++(?:{_SYNTH_SYSTEM_NAME}|{_SYNTH_WORD_NAME})\s++{_SYNTH_AUX}{_SYNTH_ANY_VERB}"
    rf"|(?:which|this|that|and|all\s+of\s+which)\s++(?:(?:{_SYNTH_SYSTEM_NAME})\s++{_SYNTH_AUX}{_SYNTH_ANY_VERB}|(?:{_SYNTH_WORD_NAME})\s++{_SYNTH_AUX}{_SYNTH_CHECK_VERB}))"
    rf"|(?:[;:—–]|\s-)\s*+(?:{_SYNTH_SYSTEM_NAME})\s++{_SYNTH_AUX}{_SYNTH_ANY_VERB})"
    rf"{_SYNTH_VERB_TAIL}",
    re.IGNORECASE)
#: Every check said to have passed, the whole sentence ("All checks passed.", "Every check passed.", "All formal checks have passed.", "Each
#: check came back clean.", "The checks all passed.", "The formal checks passed."), or the claim said to have passed them after a separator
#: ("...; this passed all checks.", "..., which passed every check."). "The safety checks passed." and "The checks cleared." (cheques) name
#: no check of this system.
_SYNTH_CHECK_KIND = r"(?:formal|automated|automatic|integrity|verification|engine|hub|z3|logic|ledger)"
_SYNTH_ALL_CHECKS_RE = re.compile(
    r"^[\W_]*(?:all|every|each)\s++(?:(?:of\s++)?(?:the|its|our|my)\s++)?(?:[\w-]+\s++)?checks?\s++(?:(?:have|has)\s++(?:all\s++)?)?"
    r"(?:passed|pass(?:es)?|succeeded|cleared|(?:came|come|comes)\s++back\s++clean|(?:are|were|is|was)\s++(?:all\s++)?(?:passed|green|clean|ok|okay))[\W_]*$"
    rf"|^[\W_]*the\s++(?:{_SYNTH_CHECK_KIND}\s++checks?\s++(?:(?:have|has)\s++)?(?:all\s++)?|checks\s++(?:(?:have|has)\s++)?all\s++)(?:passed|succeeded)[\W_]*$"
    r"|(?:[;,:—–]|\s-)\s*+(?:this|it|which|the\s++claim|this\s++claim)\s++(?:has\s++)?(?:passed|passes|cleared|clears)\s++"
    r"(?:all|every|each|the)\s++(?:of\s++the\s++)?(?:[\w-]+\s++)?checks?\s*+[.!]?[\s\"'”’)\]]*+$"
    r"|^[\W_]*(?:this|it|the\s++claim|this\s++claim)\s++(?:has\s++)?(?:passed|passes|cleared|clears)\s++(?:all|every|each|the)\s++(?:of\s++the\s++)?"
    r"(?:[\w-]+\s++)?checks?[\W_]*$", re.IGNORECASE)
#: The system named as what confirmed the claim, the whole sentence (integration gate 3): "The engine confirms this claim.", "The hub has
#: verified this.", "The solver proved the claim.", "Z3 verified it." The names that are also ordinary words of the subjects (the overseer,
#: the translator, the checker, the verifier, Z3) count only with a verb of verification ("The overseer approved this claim." may be
#: History), and every form needs the claim, 'it' or 'this' as what was confirmed ("The engine proved reliable." is content).
_SYNTH_CLAIM_OBJECT = (r"(?:it|this|that|so|the\s++claims?|this\s++claim|the\s++(?:synthesis|combined\s++answer|answer)|everything(?:\s++(?:above|here))?"
                       r"|all\s++(?:of\s++)?(?:this|it|the\s++claims))")
_SYNTH_INFRA_MAIN_RE = re.compile(
    rf"^[\W_]*(?:(?:{_SYNTH_SYSTEM_NAME})\s++{_SYNTH_AUX}{_SYNTH_ANY_VERB}|(?:{_SYNTH_WORD_NAME})\s++{_SYNTH_AUX}{_SYNTH_CHECK_VERB})\s++{_SYNTH_CLAIM_OBJECT}"
    r"[\W_]*$", re.IGNORECASE)
#: A signed result claimed for the claim ("This claim carries a signed engine result.", "It rests on a signed Z3 proof."): no agent can write
#: one, so the words are a self-report. A signed receipt of trade ("Each delivery has a signed receipt") names no engine.
_SYNTH_SIGNED_RE = re.compile(
    r"\b(?:carries|carry|has|have|bears|holds|comes\s++with|is\s++backed\s++by|rests\s++on|is\s++supported\s++by)\s++(?:a|an|the|its)\s++(?:(?:valid|verified)\s++)?"
    r"signed\s++(?:(?:(?:engine|hub|z3|solver|formal|overseer|verification)\s++)(?:result|receipt|verdict|check|proof|certificate)|result|verdict)\b", re.IGNORECASE)
#: Content before a claimed signed result other than its subject ("This claim carries ...", "It rests on ..."): the words are then written
#: after the claim's content.
_CONTENT_BEFORE_SIGNED_RE = re.compile(r"[;,:—–]|\b(?!(?:this|that|it|the|claim|statement|point|fact|figure|date|answer|synthesis|each|every|all)\b)[^\W\d_]{2,}\b",
                                       re.IGNORECASE)
#: Verification words of other languages written as a label on a claim, bracketed ("(vérifié)", "(geprüft)", "[verificado]") or closing it
#: after a separator ("...; überprüft."), read on a synthesis only (a specialist of a language may gloss a word: "checked (vérifié)").
_SYNTH_FOREIGN_WORD = (r"(?:v[ée]rifi[ée]e?s?|contr[ôo]l[ée]e?s?|confirm[ée]e?s?|gepr[üu]ft|[üu]berpr[üu]ft|best[äa]tigt|verifiziert|verificad[oa]s?|comprobad[oa]s?"
                       r"|confirmad[oa]s?|verificat[oaie]|controllat[oaie]|confermat[oaie]|gecontroleerd|geverifieerd|sprawdzon[aey])")
_SYNTH_FOREIGN_LABEL_RE = re.compile(
    rf"[\[(]\s*+{_SYNTH_FOREIGN_WORD}\s*+[.!]?\s*+[\])]|(?:[;:—–]|\s-)\s*+{_SYNTH_FOREIGN_WORD}\s*+[.!]?[\s\"'”’)\]]*+$|^[\W_]*{_SYNTH_FOREIGN_WORD}[\W_]*$",
    re.IGNORECASE)

#: Cheap pre-filter for the combinator's verdicts above.
_SYNTH_VERDICT_CUE_RE = re.compile(r"sat|entail|sign|receipt|accept|approv|pass|clear|overseer|hub|audit|logic|correct|fact|true|reliab|doubt|question|dispute"
                                   r"|certain|verif|confirm|check|accura|valid|prov|ok|\bq\.?a\b|review|right|establish|v[ée]rifi|contr[ôo]l|pr[üu]ft|best[äa]tigt"
                                   r"|comprobad|confermat|controleerd|sprawdzon", re.IGNORECASE)


def _synthesis_verdict_label(masked: str) -> Optional[VerificationLabel]:
    """The combinator's verdict label of :data:`_SYNTH_VERDICT_LABEL_RE`, :data:`_SYNTH_STATUS_KEY_RE`, :data:`_SYNTH_LEAD_VERDICT_RE` or
    :data:`_SYNTH_SELF_ASSESS_RE` in ``masked`` (quotations masked), with where it stands, or None."""
    if not _SYNTH_VERDICT_CUE_RE.search(masked):
        return None
    m = _SYNTH_LEAD_VERDICT_RE.match(masked)
    if m is not None and _LABEL_CONTENT_RE.search(masked, m.end()):
        return VerificationLabel("before", masked[:m.end()].strip()[:200])
    m = _SYNTH_SELF_ASSESS_RE.search(masked)
    if m is not None and _LABEL_CONTENT_RE.search(masked[:m.start()]):
        return VerificationLabel("after", masked[m.start():].strip()[:200])
    # the infrastructure or the checks credited with the claim, and a signed result claimed for it (integration gate 3)
    m = _SYNTH_INFRA_CREDIT_RE.search(masked) or _SYNTH_ALL_CHECKS_RE.search(masked)
    if m is not None and not _NEGATED_OR_DEONTIC_RE.search(masked[max(0, m.start() - 60):m.start()]):
        return VerificationLabel("after" if _LABEL_CONTENT_RE.search(masked[:m.start()]) else "whole", m.group(0).strip(" ,;:—–-")[:200])
    m = _SYNTH_SIGNED_RE.search(masked)
    if m is not None and not _NEGATED_OR_DEONTIC_RE.search(masked[max(0, m.start() - 60):m.start()]):
        return VerificationLabel("whole" if not _CONTENT_BEFORE_SIGNED_RE.search(masked[:m.start()]) else "after", m.group(0).strip()[:200])
    m = _SYNTH_VERDICT_LABEL_RE.search(masked) or _SYNTH_STATUS_KEY_RE.search(masked) or _SYNTH_FOREIGN_LABEL_RE.search(masked)
    if m is None:
        return None
    before, after = masked[:m.start()], masked[m.end():]
    if not _LABEL_CONTENT_RE.search(before) and not _LABEL_CONTENT_RE.search(after):
        position = "whole"
    elif not _LABEL_CONTENT_RE.search(after):
        position = "after"
    elif not _LABEL_CONTENT_RE.search(before):
        position = "before"
    else:
        position = "inside"
    return VerificationLabel(position, m.group(0).strip()[:200])


@functools.lru_cache(maxsize=8192)
def _synthesis_self_report(sentence: str) -> bool:
    if not _SYNTH_CUE_RE.search(sentence):
        return False
    masked = mask_quotations(sentence)  # a quoted certification is the quoted text's
    m = _SYNTH_NO_ERRORS_RE.search(masked)
    if m is not None and not _NEGATED_OR_DEONTIC_RE.search(masked[max(0, m.start() - 60):m.start()]):
        return True  # "It is not true that no errors were found in this synthesis" is no self-report
    subjects = list(_SYNTH_SUBJECT_RE.finditer(masked))
    if not subjects:
        return False
    for m in subjects:
        tail = _SELF_PREDICATE_TAIL_RE.match(masked, m.end())
        if tail is not None:
            after = tail.end()
            end = _SYNTH_CLAUSE_END_RE.search(masked, after)
            if _SYNTH_BY_OTHER_RE.search(masked[after:end.start() if end else len(masked)]):
                continue  # a check credited to another agent ("... by the History specialist") is that agent's, not the writer's
            if tail.group("fidelity"):
                if _FIDELITY_END_RE.match(masked, after):
                    return True
                continue
            if tail.group("check"):
                if tail.group("check").lower().endswith(("with", "against", "to")) or _CHECK_END_RE.match(masked, after):
                    return True
                continue
            complement = _SYNTH_COMPLEMENT_RE.match(masked, after)
            if _SELF_CLOSING_RE.match(masked, complement.end() if complement else after):
                return True
            continue
        if _SYNTH_FIDELITY_VERB_RE.match(masked, m.end()):
            return True
    if _positive(_INFRA_AGENT_RE, masked) or _positive(_NO_FURTHER_CHECK_RE, masked):
        return True  # "Z3 has verified this synthesis", "The hub accepted the combined answer", "The synthesis needs no further checking"
    return _SYNTH_NOTHING_RE.search(masked) is not None


def is_synthesis_self_certification(sentence: str) -> bool:
    """True when a sentence the COMBINATOR wrote (a synthesized claim, a sentence of a synthesis's text) certifies the
    combined answer's own checking: every form :func:`is_self_certification` reads in a specialist's answer, and the
    combinator's own product named as the answer itself, with the same structural limits:

    * the synthesis, the combined answer or its claims as the subject ("The synthesis has been verified.", "This synthesis
      is correct.", "The combined answer is accurate.", "Every synthesized claim was checked against the sources.", "All
      claims in this synthesis were verified.") followed directly by a copula and a checking participle, an accuracy
      adjective (closing the clause, or with "to the sources", "in every detail") or a reproduction-fidelity predicate;
    * the combined product said to reproduce or match its sources ("accurately reflects the sources", "is consistent with
      the specialists' reports") or to have passed a check ("passed every check", "has passed the hub's verification");
    * the infrastructure as the agent that passed it ("Z3 has verified this synthesis", "The hub accepted the synthesis"),
      or nothing in it left to check ("Nothing in this synthesis needs checking", "The synthesis needs no further
      checking").

    Never a check under negation or a modal ("The synthesis has not been verified", "should be checked against the
    sources"), one credited to another agent ("The synthesis was checked by the History specialist"), one quoted, or a
    synthesis of something else ("the synthesis of ammonia"). On a specialist's branch these words are content, so
    :func:`is_self_certification` (the specialists' reading) does not read them. Cached per sentence."""
    if is_self_certification(sentence):
        return True
    if _SYNTH_VERDICT_CUE_RE.search(sentence):
        masked = mask_quotations(sentence)
        if _SYNTH_ANSWER_VERDICT_RE.match(masked) or _SYNTH_INTENSE_VERDICT_RE.match(masked) or _SYNTH_INFRA_MAIN_RE.match(masked):
            # "The answer is correct.", "This has been verified." (finding 7); "This is definitely correct.", "The engine confirms this claim."
            return True
    return _synthesis_self_report(sentence) if len(sentence) <= _CACHE_MAX_CHARS else _synthesis_self_report.__wrapped__(sentence)


def verification_label(sentence: str) -> Optional[VerificationLabel]:
    """The verification-status label ``sentence`` carries, or ``None``: an agent's own checking participle written as a
    label on its text, the same way on every branch and in a synthesis, read with the sentence's quotations masked:

    * ``whole``: the sentence is nothing but the label ("Verified.", "(checked)", "[verified]", "Fact-checked and
      confirmed.", "Verification: passed."), which :func:`is_self_certification` also reads as a self-certification;
    * ``before`` its content: bracketed ("[verified] ...", "(Checked) ...") or a capitalised label closed by a colon or a
      dash ("Verified: ...", "Checked: ...", "Formally verified — ...", "VERIFIED by the Z3 engine: ...");
    * ``after`` its content: bracketed at the end ("... in August 1919 (verified).", "... [checked]"), after "as" and a
      comma ("..., as formally verified.", "..., as checked above.", "..., as verified by the engine.") or after a
      semicolon, a colon or a dash ("...; verified.", "... — checked.");
    * ``inside`` it: a bracketed label within the sentence ("The figure (verified) is 6 million."), or a check mark
      anywhere ("The treaty ✓ was signed in 1919.").

    The label's words are a checking participle ("verified", "checked", "confirmed", "validated", "certified",
    "fact-checked", "cross-checked", "source-checked", "Z3-verified", ...), with adverbs ("formally", "independently"),
    joined ("checked and verified"), credited to the infrastructure or the writer ("by Z3", "by the hub", "by me") or made
    "against the supplied text", "against the sources", "with the specialists' reports"; a status noun with one ("(accuracy
    confirmed)", "(facts checked)", "Figures verified."); a verdict ("Formally proven correct.", "(verified correct)",
    "shown to be accurate", "Checked and correct."); a status key ("Verification: passed", "Accuracy: confirmed"); or a check
    mark ("✓", "✔", "☑", "✅"), alone or with any of them. After a bare comma at the end only a label with what it was
    checked against or by whom, a verdict or a status noun counts (", checked against the sources.", ", verified by Z3.");
    a bare ", checked." may close a sentence about history. A participle under negation or a modal ("unverified", "(not
    checked)", "(accuracy not confirmed)", "(to be verified)"), credited to another agent ("..., as confirmed by Engels.",
    "(checked by the Registrar General)", "(verified by the History specialist)"), checked against a record the writer
    names ("(checked against the Registrar General's returns)"), followed by more content ("..., as later confirmed in
    1921.", "Checked at the Marne, the advance stalled.", "The census figures were, in 1925, verified.") or asked
    ("Verified?") is no label; "proved" alone and an accuracy adjective alone ("correct") are not labels here, nor is a
    cross ("✗"). A label is an agent self-report: advisory, never evidence that anything was checked (CORE-SELF-001 on a
    specialist's sentence, INT-LEDGER-029 on a synthesized claim). Cached per sentence (pure function of the text)."""
    if not sentence:
        return None
    return _verification_label(sentence) if len(sentence) <= _CACHE_MAX_CHARS else _verification_label.__wrapped__(sentence)


def synthesis_label(sentence: str) -> Optional[VerificationLabel]:
    """The verification-status label a sentence the COMBINATOR wrote carries: every label :func:`verification_label` reads
    (an engine credited with a verdict, "(Z3: proved)", and a bracketed status mark, "[OK]", included), and a bracketed
    proof verdict ("(proven)", "(proved)", "[proven]", "(formally proven)", "(proof complete)"), which a specialist's
    answer may write as the close of its own proof, read with the sentence's quotations masked. ``whole`` when the
    sentence is nothing but the label, else ``after`` (closing it), ``before`` (opening it) or ``inside``."""
    found = verification_label(sentence)
    if found is not None or not sentence:
        return found
    masked = mask_quotations(sentence.strip())
    verdict = _synthesis_verdict_label(masked)  # the engine's and the Overseer's vocabulary, a leading verdict, a self-assessment
    if verdict is not None:
        return verdict
    if not _SYNTH_PROOF_LABEL_RE.search(sentence):
        return None
    m = _SYNTH_PROOF_LABEL_RE.search(masked)
    if m is None:
        return None
    before, after = masked[:m.start()], masked[m.end():]
    if not _LABEL_CONTENT_RE.search(before) and not _LABEL_CONTENT_RE.search(after):
        position = "whole"
    elif not _LABEL_CONTENT_RE.search(after):
        position = "after"
    elif not _LABEL_CONTENT_RE.search(before):
        position = "before"
    else:
        position = "inside"
    return VerificationLabel(position, m.group(0).strip()[:200])


#: The writer's own hedges, by what they leave the statement: possible ("may have", "might have", "could have", "may be",
#: "possibly", "perhaps", "conceivably", "it is possible that") or probable ("probably", "most likely", "in all likelihood",
#: "it is likely that", "likely to have", "presumably", "arguably", "apparently", "plausibly", "appears to", "seems to",
#: "suggests"). A bare adjective ("made withdrawal likely", "a likely allocation", "an unlikely alliance", "a provisional
#: government") is the statement's content, not a hedge; "could be" may name an option ("prices could be raised").
_POSSIBLE_HEDGE_RE = re.compile(
    r"\b(?:may|might|could)\s+(?:well\s+|possibly\s+)?have\b|\b(?:may|might)\s+(?:well\s+)?be\b|\bpossibly\b|\bperhaps\b|\bconceivably\b"
    r"|\bit\s+is\s+(?:just\s+|also\s+)?possible\s+that\b",
    re.IGNORECASE)
_PROBABLE_HEDGE_RE = re.compile(
    r"\bprobably\b|\b(?:most|very|highly|quite)\s+likely\b|\bin\s+all\s+likelihood\b|\bit\s+is\s+(?:most\s+|very\s+|highly\s+)?(?:likely|probable)\s+that\b"
    r"|\blikely\s+to\s+have\b|\bpresumably\b|\barguably\b|\bapparently\b|\bplausibly\b|\b(?:appears?|seems?)\s+to\b|\bsuggest(?:s|ed)?\b",
    re.IGNORECASE)


def hedged_certainty(sentence: str) -> Optional[str]:
    """``"possible"`` or ``"probable"`` when the writer hedges ``sentence`` (:data:`_POSSIBLE_HEDGE_RE`,
    :data:`_PROBABLE_HEDGE_RE`), read with its quotations masked (a hedge inside a quotation is the quoted text's: "we all
    could have been to blame"), else ``None``. The parsers record it as the claim's agent-stated certainty, so a synthesis
    that states a hedged claim as established is named by the hub (INT-LEDGER-003). Never raises a certainty: a parser
    keeps the weaker of its own reading and this one."""
    if not sentence:
        return None
    masked = mask_quotations(sentence)
    if _POSSIBLE_HEDGE_RE.search(masked):
        return "possible"
    if _PROBABLE_HEDGE_RE.search(masked):
        return "probable"
    return None


def is_task_note(sentence: str) -> bool:
    return bool(TASK_NOTE_RE.search(sentence))


def is_note_sentence(sentence: str) -> bool:
    """A sentence that is a label about the text (from-memory disclaimer, self-certification,
    or a note that the syllabus version, cohort, level or mark was not given) rather than part
    of the argument: its core is empty once its note clauses are set aside
    (:func:`split_note_clauses`, read outside quotations). A label word somewhere in a
    substantive sentence, or inside its quotations, does not make it a note."""
    return bool(sentence.strip()) and not split_note_clauses(sentence)[0]


def is_json_shaped(sentence: str) -> bool:
    """True when ``sentence`` carries the shape of JSON: a quoted key with a JSON value and
    either a bracket or a second key-value pair. Prose that quotes a word before a colon does not qualify."""
    pairs = JSON_KEY_RE.findall(sentence)
    if not pairs:
        return False
    return len(pairs) >= 2 or any(ch in sentence for ch in "{}[]")


def is_json_block(block: str) -> bool:
    """True when ``block`` is a pasted JSON document (parses as an object or array), or opens
    and closes with brackets around at least one JSON key-value pair. The key-value shape is
    tested first, so a deeply nested block is never handed to the JSON parser when its shape
    already decides, and a block too deeply nested to parse is not JSON by parse."""
    s = block.strip()
    if not s or s[0] not in "{[" or s[-1] not in "}]":
        return False
    if JSON_KEY_RE.search(s):
        return True
    try:
        parsed = json.loads(s)
    except (ValueError, RecursionError):
        return False
    return isinstance(parsed, (dict, list))


# ------------------------------------------------------------------ pasted JSON spans

_MAX_JSON_SPAN_CHARS = 60_000
_BLANK_LINE_RE = re.compile(r"\n[ \t]*\n")
_JSON_OPENER_RE = re.compile(r"[\[{]")
#: The characters a bracket scan stops at outside a string, and inside one.
_JSON_SCAN_RE = re.compile(r'["{}\[\]\n]')
_JSON_STRING_SCAN_RE = re.compile(r'["\\\n]')


def _json_span_ends(text: str, openers: list[int]) -> dict[int, tuple[int, int, bool]]:
    """For every opening bracket offset in ``openers`` (ascending), ``(end, depth, object_child)``:
    ``end`` is the index just past the bracket that closes it, or ``-1`` when the span does not
    close before a blank line, the end of ``text`` or the size cap; ``depth`` is its bracket
    nesting depth and ``object_child`` whether a ``{`` opens directly inside it (outside a
    string). Straight double-quoted strings (with backslash escapes) are skipped so brackets
    inside them do not count; a string that runs over a line break is not JSON.

    One pass, right to left: a scan that meets a nested opener outside a string jumps straight
    to the end already computed for it (or fails with it), so every character is read about
    once whatever the nesting, and brace-like text (thousands of ``{``, unclosed fragments) can
    never make the hub quadratic. ``end`` is the one a separate depth-counting scan from that
    opener would give."""
    n = len(text)
    ends: dict[int, tuple[int, int, bool]] = {}
    for start in reversed(openers):
        limit = min(n, start + _MAX_JSON_SPAN_CHARS)
        i = start + 1
        end = -1
        depth = 1
        object_child = False
        while True:
            m = _JSON_SCAN_RE.search(text, i, limit)
            if m is None:
                break
            i = m.start()
            ch = text[i]
            if ch == '"':
                j = i + 1
                closed = False
                while j < limit:
                    s = _JSON_STRING_SCAN_RE.search(text, j, limit)
                    if s is None:
                        break
                    j = s.start()
                    c = text[j]
                    if c == "\\":
                        j += 2
                        continue
                    if c == '"':
                        closed = True
                    break  # a closing mark, or a line break inside the string: not JSON
                if not closed:
                    break
                i = j + 1
                continue
            if ch in "{[":
                nested, nested_depth, _child = ends.get(i, (-1, 0, False))
                if nested < 0 or nested > limit:
                    break
                depth = max(depth, nested_depth + 1)
                object_child = object_child or ch == "{"
                i = nested
                continue
            if ch in "}]":
                end = i + 1
                break
            if _BLANK_LINE_RE.match(text, i):  # a line break: a blank line ends the candidate span
                break
            i += 1
        ends[start] = (end, depth, object_child)
    return ends


#: A span nested deeper than this is judged by its shape alone: no JSON parser should be asked to recurse that far.
_MAX_JSON_PARSE_DEPTH = 256


def _is_json_span(span: str, *, depth: int = 0, object_child: bool = True) -> bool:
    """A pasted JSON span: parses as an object (or an array holding an object), or opens on a
    quoted key and carries a JSON key-value pair. A bracketed list of words or figures in
    prose (``[1, 2]``, ``[sic]``) is not one; neither is bare nesting (``{{{...}}}``).

    The answer is decided without parsing whenever the parse cannot change it (an object that
    does not open on a key, a key-value shape already present, an array with no object directly
    inside it), and a span nested deeper than :data:`_MAX_JSON_PARSE_DEPTH` is judged by its
    shape alone, so deeply nested brace-like text costs one cheap test per bracket."""
    s = span.strip()
    if len(s) < 4 or s[0] not in "{[" or s[-1] not in "}]":
        return False
    head = s[1:].lstrip()[:1]
    keyed = head == '"' and bool(JSON_KEY_RE.search(s))
    if s[0] == "{":
        if head not in ('"', "}"):
            return False  # an object opens on a key
        if keyed:
            return True  # an object with a key-value pair, parsed or not
    elif not object_child or "{" not in s:
        return keyed  # an array counts only when an object stands directly inside it; otherwise only the key-value shape
    if depth > _MAX_JSON_PARSE_DEPTH:
        return keyed
    try:
        parsed = json.loads(s)
    except (ValueError, RecursionError):
        parsed = None
    if isinstance(parsed, dict):
        return True
    if isinstance(parsed, list):
        return any(isinstance(item, dict) for item in parsed)
    return keyed


#: Texts longer than this are scanned afresh rather than cached, so the caches stay small whatever the agents send.
_CACHE_MAX_CHARS = 16_000


@functools.lru_cache(maxsize=512)
def _json_spans(text: str) -> tuple[tuple[int, int], ...]:
    openers = [m.start() for m in _JSON_OPENER_RE.finditer(text)]
    if not openers:
        return ()
    ends = _json_span_ends(text, openers)
    spans: list[tuple[int, int]] = []
    floor = 0
    for start in openers:
        if start < floor:
            continue  # the brackets inside a span belong to it
        end, depth, object_child = ends[start]
        if end > start and _is_json_span(text[start:end], depth=depth, object_child=object_child):
            spans.append((start, end))
            floor = end
    return tuple(spans)


_BRACKET_SCAN_RE = re.compile(r'["{}\[\]]')
_BRACKET_STRING_RE = re.compile(r'["\\]')


def bracket_match_ends(text: str) -> dict[int, Optional[int]]:
    """For every ``{`` and ``[`` of ``text``, the index just past the bracket of the same kind
    that closes it, or ``None`` when it never closes or a bracket of the other kind closes first.
    Straight double-quoted strings (backslash escapes honoured, line breaks allowed) are skipped,
    so brackets inside them do not count.

    One right-to-left pass: a scan that meets a nested opener jumps to the end already computed
    for it, so the whole map costs about one read of ``text`` however deeply or often brackets
    nest. It gives, for each opener, the answer of a separate stack-based scan from that opener
    (the History sentence splitter's ``_balanced_end``), without that scan's quadratic cost on
    brace-like text."""
    openers = [m.start() for m in _JSON_OPENER_RE.finditer(text)]
    n = len(text)
    ends: dict[int, Optional[int]] = {}
    for start in reversed(openers):
        want = "}" if text[start] == "{" else "]"
        i = start + 1
        end: Optional[int] = None
        while True:
            m = _BRACKET_SCAN_RE.search(text, i)
            if m is None:
                break
            i = m.start()
            ch = text[i]
            if ch == '"':
                j = i + 1
                while True:
                    q = _BRACKET_STRING_RE.search(text, j)
                    if q is None:
                        j = n
                        break
                    j = q.start()
                    if text[j] == "\\":
                        j += 2
                        continue
                    break
                if j >= n:
                    break  # the string never closes
                i = j + 1
                continue
            if ch in "{[":
                nested = ends.get(i)
                if nested is None:
                    break
                i = nested
                continue
            if ch == want:
                end = i + 1
            break  # the closing bracket, or one of the other kind
        ends[start] = end
    return ends


def find_json_spans(text: str) -> list[tuple[int, int]]:
    """``(start, end)`` of every pasted JSON span of ``text``, in order.

    A span opens with ``{`` or ``[``, closes with the matching bracket without crossing a
    blank line, and is JSON by :func:`_is_json_span`. Spans are found wherever they stand,
    glued to prose included; the brackets inside a span belong to it. Parsers cut
    sentences at these spans and mask them before reading quotation marks, so a pasted
    receipt's strings are never quotations and the prose around it is segmented as prose.
    Bracket matching is one linear pass per text (:func:`_json_span_ends`) and the answer is
    cached per text, since every parser and pack asks it of the same paragraphs and sentences.
    """
    if "{" not in text and "[" not in text:
        return []
    return list(_json_spans(text) if len(text) <= _CACHE_MAX_CHARS else _json_spans.__wrapped__(text))


def mask_json_spans(text: str, fill: str = " ") -> str:
    """``text`` with every pasted JSON span replaced by ``fill`` character for character
    (line breaks kept), so offsets into the result are offsets into ``text``."""
    spans = find_json_spans(text)
    if not spans:
        return text
    out = list(text)
    for a, b in spans:
        for i in range(a, b):
            if out[i] != "\n":
                out[i] = fill
    return "".join(out)


def split_json_spans(text: str) -> list[tuple[str, bool]]:
    """``text`` cut into ``(piece, is_json)`` pieces in order: every pasted JSON span is one
    piece flagged ``True``, the prose between spans is flagged ``False``; blank pieces are
    dropped. The pieces are the writer's text, verbatim apart from surrounding whitespace."""
    pieces: list[tuple[str, bool]] = []
    cursor = 0
    for a, b in find_json_spans(text):
        prose = text[cursor:a].strip()
        if prose:
            pieces.append((prose, False))
        pieces.append((text[a:b].strip(), True))
        cursor = b
    tail = text[cursor:].strip()
    if tail:
        pieces.append((tail, False))
    return pieces


# ------------------------------------------------------------------ note clauses

#: A parenthetical or a clause after a semicolon/dash that can carry a note inside a longer sentence (kept for callers;
#: :func:`split_note_clauses` reads the same shapes on the sentence with its quotations masked).
_CLAUSE_RE = re.compile(r"\s*\([^()]*\)|\s*[;—–]\s*[^;—–()]+")
#: A sentence-initial label ("From memory, the mark stood at ...", "Quoting from memory, the king boasts ..."): the
#: words up to the comma or colon.
LEADING_MEMORY_LABEL_RE = re.compile(r"^\s*(?:\w+ing\s+)?(?:from (?:memory|recollection)|as (?:I|far as I) recall|if memory serves)\s*[,:]\s*", re.IGNORECASE)
#: A comma-bounded label inside a sentence (", from memory about 800 million gold marks," or ", from memory,"):
#: only the label words are removed, so the figure that follows stays in the substance.
INLINE_MEMORY_LABEL_RE = re.compile(r",\s*(?:from (?:memory|recollection)|as (?:I|far as I) recall|if memory serves)\b(?=[\s,.;:])", re.IGNORECASE)
_CHECK_PARTICIPLE = r"(?:checked|verified|confirmed|corroborated|validated|cross[- ]checked|double[- ]checked|re-?checked)"
#: What a check is made against ("against your notes", "with the statistical yearbooks"): part of the label phrase.
_CHECK_COMPLEMENT = r"(?:\s+(?:against|with)\s+[^,;:.()!?]{1,80}?(?=\s+before\b|\s*[,;:.()!?]|\s*$))?"
#: The phrases that make a clause the method's own label rather than part of the argument: a from-memory phrase
#: ("from memory", "given from memory", "as I recall"), an instruction to check ("verify them against your notes",
#: "; check your notes", ", so check them"), a deontic or negated check, which is a disclaimer ("should be checked",
#: "must be verified", "have not been checked", "unverified"), and "illustrative". A phrase alone never makes a sentence
#: a note: :func:`_label_shaped` also asks that nothing but label filler is left once the phrases are removed.
LABEL_PHRASE_RE = re.compile(
    r"\b(?:(?:quoted|quoting|given|giving|cited|citing|stated|recalled|written|reproduced|taken)\s+)?from (?:memory|recollection)\b"
    r"|\bas (?:I|far as I) (?:can )?(?:recall|remember)\b|\bif memory serves\b|\bto (?:the best of )?my (?:recollection|memory)\b"
    r"|(?:^|(?<=[(;:,—–])|\b(?:so|and|then|please|but)\s)\s*(?:please\s+)?(?:verify|check|confirm|cross[- ]check|double[- ]check|corroborate)\b"
    rf"(?:\s+(?:them|these|this|it|those|each|all|every|any|one)\b(?:\s+(?:one|ones|of|them|these|{_ITEMS})\b)*)?{_CHECK_COMPLEMENT}"
    r"|\b(?:should|must|needs?\s+to|ought\s+to|has\s+to|have\s+to|will\s+need\s+to|are\s+to|is\s+to|yet\s+to|still\s+to|to)\s+"
    rf"(?:(?:still|first|all|each|independently|carefully|also|then)\s+)*(?:have\s+)?be(?:en)?\s+(?:\w+ly\s+)?{_CHECK_PARTICIPLE}{_CHECK_COMPLEMENT}"
    rf"|\b(?:has|have|had|is|are|was|were)(?:\s+not|n['’]t)\s+(?:yet\s+)?(?:been\s+)?(?:\w+ly\s+)?{_CHECK_PARTICIPLE}{_CHECK_COMPLEMENT}"
    rf"|\bnot\s+(?:yet\s+)?(?:been\s+)?{_CHECK_PARTICIPLE}{_CHECK_COMPLEMENT}"
    r"|\bun(?:verified|checked|confirmed|corroborated)\b|\billustrative\b",
    re.IGNORECASE,
)
#: Words a label may carry besides its label phrase: determiners, pronouns, auxiliaries, connectives, the answer's own
#: items ("dates", "figures", "quotations") and parts ("this paragraph"), and the verbs of giving and citing.
_LABEL_FILLER = frozenset("""
a an the this that these those all each every any some both its it their them they i we my our your his her own one ones
of in on at to for from with against by about before after until unless when once as so and or but nor though although while
which who whom whose is are was were be been being am has have had do does did will would shall should must may might can could
need needs ought not no yet still also only just here above below given cited quoted stated recalled recall recalls give gives
gave giving cite cites citing quote quotes quoting state states stating taken take takes use used using rely relied relying
reproduce reproduced written write wrote put figure figures date dates number numbers statistic statistics quotation quotations
fact facts detail details data year years total totals estimate estimates item items value values citation citations reference
references source sources claim claims example examples statement statements paragraph paragraphs answer answers response text
essay report outline summary section passage note notes examination exam assessment please accordingly therefore further
independently carefully first again thereby then verify verified check checked confirm confirmed memory recollection
reported reports marked marks labelled labeled flagged treated left presented offered
""".split())
_NOTE_TOKEN_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")
#: "<subject> is/are (given) from memory" as the clause's whole predicate: "The causes of the banking crisis of 1931 are
#: from memory", "Dates other than the poem's own are from memory, so check your notes".
_PREDICATE_LABEL_RE = re.compile(
    r"^\s*(?P<subject>[^,;:()]{1,160}?)\s+(?:is|are|was|were|has been|have been)\s+(?:(?:all|largely|mostly|partly|entirely|wholly|only|both)\s+)?"
    r"(?:(?:given|quoted|cited|stated|recalled|taken|reproduced)\s+)?from (?:memory|recollection)\b(?P<rest>[^;]*)$",
    re.IGNORECASE,
)
#: A subject that is itself a clause ("Wordsworth wrote that the images ...") is not a label's subject.
_SUBORDINATE_RE = re.compile(r"\b(?:that|which|who|whom|because|since|when|while|whether|if|although|though|where)\b", re.IGNORECASE)
#: A bare "from memory" closing a dated sentence ("... in February 1932 from memory."). A match starts only where no whitespace
#: precedes (``(?<!\s)``): the leftmost match of the blanks before the label starts at the first blank of their run, so the
#: matches are those of the pattern without the anchor, read in linear time (the unanchored search read the rest of a run of n
#: blanks from each of them, n² steps; integration gate 1, parser-safety-3).
_TRAILING_BARE_LABEL_RE = re.compile(r"(?<!\s)\s+(?:(?:quoted|given|cited|stated|recalled)\s+)?from (?:memory|recollection)(?=[.!?]?[\"'”’»)\]]*\s*$)", re.IGNORECASE)
#: A note on how the answer was composed (quotations masked, terminal punctuation removed): its subject is the answer, one of
#: its parts or a received report ("The historical setting", "The judgement on which decade ...", "The English specialist's
#: paragraph"), its whole predicate is authorship or provenance ("is my own addition", "is not part of that paragraph", "is
#: from memory as well", "is from the hub", "was relayed through the hub"), optionally followed by ", not part of that
#: paragraph". Anything else asserted about the subject ("..., and it shows that ...") keeps the sentence substantive.
_PROVENANCE_REPORT_NOUNS = r"(?:paragraph|report|answer|response|analysis|account|contribution|material|outline|summary)"
_PROVENANCE_NOT_PART = (rf"not\s+(?:part\s+of|from|in|taken\s+from|drawn\s+from|stated\s+in|given\s+in)\s+(?:that|this|the|his|her|its|their|my|our)\s+"
                        rf"(?:[a-z'’-]+\s+){{0,2}}?{_PROVENANCE_REPORT_NOUNS}")
_PROVENANCE_NOTE_RE = re.compile(
    r"(?:(?:but|and|so|also|note(?:\s+that)?|please\s+note(?:\s+that)?)[,:\s]+)?"
    r"(?:(?:the|my|our)\s+(?:[a-z]+\s+)?(?:specialist|colleague|peer)(?:'s|’s)\s+(?:paragraph|report|reading|analysis|account|words|quotations?|answer|contribution|material)"
    r"|(?:the|this|my|our|that|these|those)\s+(?:[a-z'’-]+\s+){0,2}?"
    r"(?:setting|context|background|judge?ments?|verdict|conclusion|outline|answer|paragraph|response|summary|framing|additions?|section|reading|analysis"
    r"|interpretation|report|material)(?:\s+(?:on|of|about|for|in|above|below|here)\b[^,;:]{0,120}?)?)"
    r"\s+(?:is|are|was|were)\s+(?:also\s+|entirely\s+|wholly\s+|all\s+|likewise\s+|itself\s+|simply\s+)?"
    r"(?:(?:my|our)\s+own(?:\s+(?:addition|additions|work|view|judge?ment|reading|inference|framing|contribution|interpretation|summary|context|gloss))?"
    r"|mine|ours|(?:an?|my|our)\s+(?:own\s+)?(?:addition|additions|supplement|gloss)"
    rf"|{_PROVENANCE_NOT_PART}"
    r"|from\s+(?:memory|recollection|the\s+hub|my\s+own\s+(?:knowledge|recollection|reading|memory)|that\s+paragraph|that\s+report"
    r"|the\s+(?:[a-z]+\s+)?(?:specialist|colleague|peer)(?:'s|’s)?(?:\s+(?:paragraph|report))?)"
    r"|(?:taken|drawn|quoted|relayed|forwarded|supplied|received|passed\s+on)\s+(?:from|through|by|via)\s+(?:the\s+hub|that\s+paragraph|that\s+report"
    r"|the\s+(?:[a-z]+\s+)?(?:specialist|colleague|peer|router)(?:'s|’s)?(?:\s+(?:paragraph|report))?))"
    r"(?:\s+(?:as\s+well|too|also|alone))?"
    rf"(?:\s*,\s*(?:and\s+|but\s+)?(?:it\s+is\s+|they\s+are\s+)?{_PROVENANCE_NOT_PART})?",
    re.IGNORECASE,
)


#: A quoted label ("from memory", "unverified", "approximate"): inside a provenance note it is read as the label it is.
_QUOTED_LABEL_RE = re.compile(
    r"\s*(?:(?:given|quoted|cited|stated|written|reproduced|taken)\s+)?(?:from\s+(?:memory|recollection)|un(?:verified|checked|confirmed|corroborated)"
    r"|approximate|approximations?|approx\.?|estimates?|estimated|illustrative|provisional|to\s+be\s+(?:checked|verified|confirmed)|not\s+(?:yet\s+)?(?:checked|verified|confirmed))"
    r"\s*[.,;:!?]*\s*",
    re.IGNORECASE,
)


def is_label_quotation(inner: str) -> bool:
    """True when a quotation's words are nothing but a label ("from memory", "unverified", "approximate"): a writer who
    quotes a colleague's label ("That account marks its figures as "from memory"") relays the label, not evidence."""
    return len(inner) <= 60 and _QUOTED_LABEL_RE.fullmatch(inner) is not None


#: The items a provenance note speaks of.
_PROV_ITEMS = r"(?:figures?|dates?|numbers?|statistics?|quotations?|quotes?|excerpts?|estimates?|totals?|details?|data|claims?|facts?)"
#: A received report or its writer as the subject: "That account", "the History specialist's paragraph", "the colleague".
_PROV_REPORT = (r"(?:(?:that|this|the|its)\s+(?:(?:history|english|peer|colleague['’]s|specialist['’]s|relayed|received|forwarded|other)\s+)?"
                r"(?:account|report|paragraph|contribution)"
                r"|(?:the|my|our)\s+(?:[a-z]+\s+)?(?:specialist|colleague|peer)(?:(?:'s|’s)\s+(?:paragraph|report|account|answer|analysis|contribution))?)")
#: The items of a received report, or of the answer located in it: "its figures", "the History specialist's figures",
#: "that account's dates", "the quotations above", "my figures". A bare subject ("the census figures") is not one: a source's
#: precision is a historian's claim.
_PROV_ITEM_SUBJECT = (r"(?:(?:(?:the|my|our)\s+(?:[a-z]+\s+)?(?:specialist|colleague|peer)(?:'s|’s)|(?:that|this|the)\s+(?:(?:history|english|peer|relayed|received)\s+)?"
                      r"(?:account|report|paragraph)(?:'s|’s)|its|their)\s+(?:own\s+)?(?:[a-z]+\s+)?" + _PROV_ITEMS +
                      r"|(?:the|my|our|these|all\s+(?:the|my)|all|every|each)\s+(?:[a-z]+\s+)?" + _PROV_ITEMS +
                      r"\s+(?:above|here|below|(?:used|given|cited|quoted)(?:\s+(?:here|above|below))?|in\s+(?:this|my)\s+(?:paragraph|answer|response|essay))"
                      r"|(?:my|our)\s+" + _PROV_ITEMS + r")")
#: The answer's quotations or figures, determined or not ("Quotations are from the supplied extract"), for a provenance predicate only.
_PROV_ANY_ITEMS = r"(?:(?:the|my|our|these|all(?:\s+(?:the|my))?|every|each)\s+)?(?:[a-z]+\s+)?" + _PROV_ITEMS + r"(?:\s+(?:above|here|below|used|given|cited|quoted))?"
#: Where a provenance predicate says the items come from: the supplied text, a received report, the hub, memory.
_PROV_SOURCE = (r"(?:(?:the\s+)?(?:supplied|given|provided|original|source)\s+(?:text|extract|poem|passage|sonnet|document|edition)"
                r"|the\s+(?:poem|extract|passage|sonnet|text)|the\s+hub|memory|recollection|(?:that|this)\s+(?:account|report|paragraph)"
                r"|(?:the|my|our)\s+(?:[a-z]+\s+)?(?:specialist|colleague|peer)(?:'s|’s)?(?:\s+(?:paragraph|report|account|answer))?"
                r"|the\s+(?:(?:history|english|peer|relayed|received|forwarded)\s+)+(?:report|paragraph|account))")
_PROVENANCE_EXTRA_RE = re.compile(
    r"(?:(?:but|and|so|also|note(?:\s+that)?|please\s+note(?:\s+that)?)[,:\s]+)?(?:"
    # a received report labelling its items: "That account marks its figures as "from memory"", "labels its figures from memory"
    rf"{_PROV_REPORT}\s+(?:itself\s+|also\s+|explicitly\s+|openly\s+|clearly\s+)?"
    r"(?:marks?|marked|labels?|labell?ed|flags?|flagged|tags?|tagged|describes?|described|presents?|presented|gives?|gave|lists?|listed|offers?|offered"
    r"|qualifies|qualified|notes?|noted|calls?|called|treats?|treated|introduces?|introduced|states?|stated|reports?|reported)"
    rf"\s+(?:all\s+(?:of\s+)?)?(?:its|their|his|her|the|these|those)\s+(?:own\s+)?(?:[a-z]+\s+)?{_PROV_ITEMS}\s+(?:as\s+(?:being\s+)?)?"
    r"(?:labelq|from\s+(?:memory|recollection)|un(?:verified|checked|confirmed)|approximate|provisional|illustrative|estimates?|recollections?)"
    # a report's items, or the answer's located items, with a verification status: "Its figures are marked "from memory"", "are reported unverified"
    rf"|{_PROV_ITEM_SUBJECT}\s+(?:is|are|was|were)\s+(?:all\s+|both\s+|also\s+|therefore\s+|only\s+)?"
    r"(?:(?:reported|given|left|presented|treated|offered|marked|labell?ed|flagged|cited|relayed|passed\s+on|kept)\s+)?(?:as\s+)?"
    r"(?:labelq|un(?:verified|checked|confirmed|corroborated)|provisional|approximate|illustrative|from\s+(?:memory|recollection))"
    # where the answer's items come from: "Quotations are from the supplied extract", "The figures above come from the History specialist's paragraph"
    rf"|{_PROV_ANY_ITEMS}\s+(?:(?:is|are|was|were)\s+(?:all\s+|both\s+|also\s+|only\s+)?(?:(?:taken|drawn|quoted|copied|reproduced|cited|given|relayed)\s+)?(?:from|in)"
    rf"|(?:comes?|came|derives?|derived|(?:is|are)\s+derived)\s+(?:only\s+|entirely\s+|directly\s+|all\s+)?from)\s+{_PROV_SOURCE}"
    # the answer's word count: "The word count is approximate."
    r"|(?:the|my|this|its)\s+(?:word[- ]count|word\s+total|count|length)(?:\s+(?:of|for)\s+(?:this|the|my)\s+(?:paragraph|answer|response|essay))?"
    r"\s+(?:is|was)\s+(?:only\s+|also\s+)?(?:an?\s+)?(?:approximate|approximation|estimate|estimated|rough|indicative)"
    r")(?:\s+(?:as\s+well|too|also|alone))?",
    re.IGNORECASE,
)
#: Clauses that may close a provenance note after a comma or semicolon: ", not from the poem", ", so they are reported unverified"
#: (label-shaped), "I have not checked them", "check them before use".
_PROV_TRAIL_RE = re.compile(
    r"(?:(?:and|but|so)\s+)?(?:(?:it|they)\s+(?:is|are)\s+)?not\s+(?:from\s+|in\s+|part\s+of\s+|taken\s+from\s+)?(?:the|my|this|that|its|their)\s+"
    r"(?:[a-z'’-]+\s+){0,2}?(?:poem|text|extract|passage|sonnet|novel|play|argument|analysis|reading|paragraph|answer|report|account)"
    r"|(?:and\s+|but\s+|so\s+)?(?:I|we)\s+(?:have\s+not|haven't|did\s+not|didn't|could\s+not|couldn't|cannot|can't)\s+(?:yet\s+)?(?:checked|verified|confirmed|check|verify|confirm)\b[^,;:]{0,60}",
    re.IGNORECASE,
)


def _provenance_body(sentence: str) -> str:
    """``sentence`` with its terminal punctuation removed, every quotation replaced by one placeholder word and a quoted
    label (:func:`is_label_quotation`) by the word ``labelq``, whitespace collapsed: the text a provenance note is read on."""
    parts: list[str] = []
    cursor = 0
    for a, b, inner in find_quotation_spans(sentence):
        parts.append(sentence[cursor:a])
        parts.append(" labelq " if is_label_quotation(inner) else " xquotex ")
        cursor = b
    parts.append(sentence[cursor:])
    text = "".join(parts)
    text = text[: len(text) - _terminal_len(text)]
    return re.sub(r"\s+([,;])", r"\1", " ".join(text.split()))


def is_provenance_note(sentence: str) -> bool:
    """True when ``sentence`` speaks only of how the answer was composed or of what a received report says about its own
    items: "The historical setting is my own addition, not part of that paragraph.", "The judgement on which decade saw
    the most decisive expansion is from memory as well", "The English specialist's paragraph is from the hub", "That
    account marks its figures as "from memory", so they are reported unverified." (the quoted label read as the label it
    is), "The History specialist's figures are from memory", "Quotations are from the supplied extract", "The figures
    above come from the History specialist's paragraph, not from the poem.", "The word count is approximate.". Read with
    quotations masked; closing clauses that are notes themselves (", not from the poem", ", so they are reported
    unverified", "I have not checked them") are set aside first. :func:`split_note_clauses` applies it to what is left
    once the label clauses are set aside, so "...; verify it before use" beside it still leaves a note, on every branch and
    in the channel's word count. A subject that is not the answer, its located items or a received report ("The census
    figures are approximate") and a predicate that asserts anything else stay substantive."""
    if len(sentence) > 1200:
        return False
    body = _provenance_body(sentence)
    if not body or len(body) > 400:
        return False
    if _PROVENANCE_NOTE_RE.match(body) is None and _PROVENANCE_EXTRA_RE.match(body) is None:
        return False  # no prefix is a provenance clause, so no clause can be left once closing notes are set aside
    for _ in range(4):
        if _PROVENANCE_NOTE_RE.fullmatch(body) is not None or _PROVENANCE_EXTRA_RE.fullmatch(body) is not None:
            return True
        cut = max(body.rfind(","), body.rfind(";"))
        if cut <= 0:
            return False
        tail = body[cut + 1:].strip()
        if not tail or not (_PROV_TRAIL_RE.fullmatch(tail) or _label_shaped(tail)):
            return False
        body = body[:cut].rstrip()
    return False


# ---- notes read by what they say, not by a lead word (c1: hi-t14's "Casualty and cost figures are left out, because I cannot confirm
# exact numbers here; take them from your textbook and cite them.", ess-t14's "Real-world weight: I have no verified source ...", ge-t14's
# decline, offer and request to send work back). Each shape is closed and states no figure: a sentence holding a digit is never read as
# one, so a figure an answer states is never taken out of its checks; the parsers role such a sentence 'other', the channel leaves it out
# of a word or paragraph bound (``split_note_clauses``), and no synthesis is charged for leaving it out.
_NOTE_SHORT_LABEL_RE = re.compile(r"^[\W_]*+[A-Za-z][\w’'-]*+(?:\s++[\w’'-]++){0,3}\s*+:\s++")
_ANSWER_NOTE_RES = (
    # an omission of part of the answer for want of a confirmed source: "Casualty and cost figures are left out, because I cannot confirm
    # exact numbers here", "The 1924 figures are omitted as I could not verify them"
    # (the writer's reason, or "here" / "in this answer", is required: "Women were excluded." is history, not a note)
    re.compile(r"^(?:[^\W\d_][\w’'-]*+\s++){1,8}?(?:is|are|was|were|has\s++been|have\s++been)\s++(?:deliberately\s++|also\s++)?"
               r"(?:left\s++out|omitted|not\s++(?:included|given|stated|shown|covered|quoted)|excluded)"
               r"(?:\s*+,?\s*+(?:because|as|since|for)\s++I\s++(?:cannot|can['’]t|can\s++not|could\s++not|couldn['’]t|do\s++not|don['’]t|did\s++not"
               r"|am\s++unable\s++to|was\s++unable\s++to)\s++(?:confirm|verify|check|find|source|give|state)\b[^;]*+"
               r"|\s++(?:here|from\s++(?:this|the|my)\s++answer|in\s++(?:this|the|my)\s++answer)\b[^;]*+)$", re.IGNORECASE),
    # the writer has no source for what was asked, or left it out: "I have no verified source in this session for ...", "I have left
    # both out rather than estimate them, so there is no working to show for them"
    re.compile(r"^I\s++(?:have|had|found|could\s++find|can\s++find)\s++no\s++(?:(?:verified|reliable|confirmed|approved|checked|available|"
               r"trustworthy)\s++)?(?:source|figure|data|record|reference|statistic)s?\b[^;]*+$"
               r"|^I\s++(?:do\s++not|don['’]t|did\s++not|didn['’]t)\s++have\s++(?:a\s++|any\s++)?(?:(?:verified|reliable|confirmed)\s++)?"
               r"(?:source|figure|data|record)s?\b[^;]*+$"
               r"|^I\s++(?:have\s++|['’]ve\s++)?(?:left|kept)\s++(?:both|them|it|these|those|this|that|the\s++[\w-]++(?:\s++[\w-]++)?)\s++out\b[^;]*+$",
               re.IGNORECASE),
    # a decline of the deliverable or of part of it: "I can't write the analysis or the conclusion sections, ... because ..."
    re.compile(r"^I\s++(?:can['’]t|cannot|can\s++not|won['’]t|will\s++not|am\s++(?:not\s++able|unable)\s++to|must\s++not|should\s++not|shouldn['’]t)"
               r"\s++(?:write|calculate|do|complete|produce|give\s++you|provide|draft|answer|carry\s++out|work\s++out|compute|finish|submit|"
               r"prepare|create)\b[^;]*+$", re.IGNORECASE),
    # an offer of help: "I can help you work through both, and check your own working and drafts", "I will check the method"
    re.compile(r"^I\s++(?:can|could|will|would|['’]ll|am\s++happy\s++to|would\s++be\s++(?:happy|glad)\s++to)\s++(?:also\s++)?"
               r"(?:help|check|look\s++(?:at|over)|go\s++through|work\s++through|review|comment\s++on|mark|give\s++(?:you\s++)?feedback)\b[^;]*+$",
               re.IGNORECASE),
    # a request to send work back: "... and send me your distance ranks, pedestrian ranks, d values and Σd²", "paste it here for feedback"
    # (to the writer: "send me", "... back", "... here"; "Firms share your data" is no request)
    re.compile(r"^[^;]*?\b(?:send|paste|share|upload|post|show)\s++(?:me\b|(?:it|them|this|that)\s++(?:back|here|to\s++me)\b|back\b|here\b"
               r"|your\s++[^;.]{1,80}?\s++(?:back|here|to\s++me)\b)[^;]*+$", re.IGNORECASE),
    # the student's own work is the student's: "the writing and the calculation are yours", "The interpretation ... has to be yours"
    re.compile(r"^[^;]*?\b(?:is|are|has\s++to\s++be|have\s++to\s++be|must\s++be|should\s++be|needs?\s++to\s++be)\s++(?:entirely\s++|all\s++)?"
               r"(?:yours|your\s++own(?:\s++work)?)\s*+$", re.IGNORECASE),
    # the writer cannot check what was asked and so left it out: "I cannot check current worldwide numbers in this session, so I have not
    # included any." (c2 bi-t15, after a short label "On the asthma figures:")
    re.compile(r"^I\s++(?:cannot|can['’]t|can\s++not|could\s++not|couldn['’]t|am\s++unable\s++to|was\s++unable\s++to|have\s++no\s++way\s++to)\s++"
               r"(?:check|confirm|verify|source|find|access)\b[^;]*?,?\s*+(?:so|and|therefore)\s++(?:I\s++)?(?:have\s++|['’]ve\s++)?"
               r"(?:not\s++(?:included|given|stated|used|quoted|listed)|left\s++(?:them|it|these|those|this|that)\s++out|omitted)\b[^;]*+$", re.IGNORECASE),
    # a pointer to where the student should take a figure from: "For a real case with figures, check your textbook or ask your teacher"
    re.compile(r"^(?:for\s++[^,;]{1,80},\s*+)?(?:please\s++)?(?:check|consult|ask|use)\s++(?:your|a)\s++(?:textbook|teacher|course\s++notes|class\s++notes"
               r"|notes)\b[^;]*+$", re.IGNORECASE),
    # an examiner's rule on the length of the student's own work: "Examiners stop reading at 2,500 words, and that limit covers ..."
    re.compile(r"^(?:examiners?|markers?|moderators?)\s++(?:will\s++)?(?:stop|only)\s++read(?:ing)?\b[^;]*+$", re.IGNORECASE),
)
#: A clause after a semicolon that only points the student to where the omitted items can be found: "take them from your textbook and cite
#: them", "check them in your notes".
_NOTE_POINTER_CLAUSE_RE = re.compile(r"^(?:and\s++|so\s++|please\s++)?(?:take|check|find|look\s++(?:them|it)\s++up|get|add|cite|use)\s++(?:them|it|these|those)\b"
                                     r"[^;]*+$", re.IGNORECASE)
_NOTE_DIGIT_RE = re.compile(r"\d")
#: A count of words ("2,500 words", "a 350-word limit"): the length rule an examiner's remark states, not a figure of the answer's content.
_WORD_COUNT_FIGURE_RE = re.compile(r"\d[\d,]*+(?:\s++|-)words?\b", re.IGNORECASE)


def is_answer_note(sentence: str) -> bool:
    """True when ``sentence`` is a note about the answer itself, read by what it says (:data:`_ANSWER_NOTE_RES`), whatever its lead
    word: an omission for want of a confirmed source ("Casualty and cost figures are left out, because I cannot confirm exact numbers
    here; take them from your textbook and cite them."), the writer having no source for what was asked or leaving it out, a decline of
    the deliverable or of part of it, an offer of help, a request to send work back, a remark that the student's work is the student's,
    a pointer to the textbook or the teacher, an examiner's rule on the length of the student's work. A short label before it ("Real-world
    weight: I have no verified source ...") is read past. Quotations are masked first; a sentence that holds a digit, or more than one
    clause after a semicolon that is not a pointer to where the items can be found, is never one."""
    if not sentence or len(sentence) > 600:
        return False
    masked = mask_quotations(sentence).strip()
    if _NOTE_DIGIT_RE.search(_WORD_COUNT_FIGURE_RE.sub(" words", masked)):
        return False  # a figure the answer states is never taken out of its checks (a count of words aside)
    body = masked[: len(masked) - _terminal_len(masked)].strip()
    label = _NOTE_SHORT_LABEL_RE.match(body)
    if label is not None:
        body = body[label.end():]
    if not body:
        return False
    head, _sep, tail = body.partition(";")
    if tail and not all(_NOTE_POINTER_CLAUSE_RE.match(c.strip()) for c in tail.split(";") if c.strip()):
        return False
    head = head.strip()
    return any(rx.match(head) for rx in _ANSWER_NOTE_RES)


#: The decline shape of :data:`_ANSWER_NOTE_RES` (its third pattern): "I can't write ...", "I cannot write your introduction ...".
_DECLINE_RE = _ANSWER_NOTE_RES[2]


def declined_deliverable(response: str) -> Optional[str]:
    """The sentence with which ``response`` declines the deliverable it was asked for, or None: one of the first three sentences of
    its first paragraph is a decline (:func:`is_answer_note`'s decline shape: "I can't write the analysis or the conclusion sections,
    ... because the analysis and the report must be entirely your own work.", "I cannot write your introduction, your global issue
    statement or any sentence you would say on the day."). A reader of the request's bounds (the channel) can then hold the
    deliverable as declined, not as a piece of the requested length (c1 ge-t14, breadth ll-3). Quotations are masked first."""
    if not response:
        return None
    first = re.split(r"\n\s*\n", response.lstrip()[:4000], maxsplit=1)[0]
    for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", first)[:3]:
        masked = mask_quotations(sentence).strip()
        body = masked[: len(masked) - _terminal_len(masked)].strip()
        if body and not _NOTE_DIGIT_RE.search(body) and _DECLINE_RE.match(body.partition(";")[0].strip()):
            return sentence.strip()
    return None


#: Remarks that frame the answer rather than state its content: practice or invented data, the course level the writer assumed, the
#: answer's own form or method, provisional marks. A parser never makes one the point of its paragraph (the claim after it is), so
#: no synthesis is charged for leaving it out, and its role is kept (a synthesis may carry it beside the figures it frames).
_FRAMING_RES = (
    re.compile(r"^(?:all\s++(?:the\s++|these\s++)?|the\s++|these\s++)?(?:figures|data|numbers|values|prices|names|table|case|example|scenario)"
               r"(?:\s++(?:below|above|here|used|given))?\s++(?:is|are)\s++(?:all\s++)?(?:practice|invented|fictional|fictitious|made[- ]up|hypothetical"
               r"|illustrative|imaginary)\b", re.IGNORECASE),
    re.compile(r"^I\s++(?:have\s++)?assumed\s++(?:HL|SL|higher\s++level|standard\s++level|the\s++(?:HL|SL|higher|standard)\b)", re.IGNORECASE),
    re.compile(r"\bso\s++I\s++(?:have\s++)?(?:worked|answered|written)\s++(?:exactly|in\s++exact\s++form|without\s++a\s++(?:GDC|calculator))\b", re.IGNORECASE),
    re.compile(r"^every\s++answer\s++(?:below|above|here)\s++is\b", re.IGNORECASE),
    re.compile(r"^(?:the\s++)?(?:tags|marks?|mark\s++allocations?)\b[^;]{0,60}?\b(?:is|are)\s++(?:an?\s++)?provisional\b", re.IGNORECASE),
    # the case's places, people or figures are fictional (round 9, c2): "Ostrel is a fictional country and its figures are practice data,
    # so ...", "The Wendle Brook, Marsh Lane Bridge and both storms are fictional practice data.", "The [1] tags are illustrative mark points
    # for this practice question, not an official markscheme." (a bounded subject with no figure, a copula, the framing word)
    # (the framing word closes its clause or names the case's own kind of thing: "invented adjectives" and "was made up to the mark" are no
    # framing)
    re.compile(r"^[^\d;:]{1,120}?\s(?:is|are|was|were)\s++(?:all\s++|both\s++)?(?:an?\s++)?(?:fictional|fictitious|invented|imaginary|hypothetical"
               r"|made[- ]up)(?:\s++(?:for\s++practice|(?:practice\s++)?(?:data|figures|places?|countr(?:y|ies)|compan(?:y|ies)|firms?|towns?|cit(?:y|ies)"
               r"|names?|people|persons?|characters?|cases?|scenarios?|examples?|econom(?:y|ies)|rivers?|regions?|schools?|businesses|business)))?"
               r"(?:\s*+[,.!]|\s*+$|\s++(?:and|so|for|here|in\s++this)\b)", re.IGNORECASE),
    re.compile(r"^(?:the\s++)?(?:\[\s*+\d{1,2}\s*+\]\s++)?(?:tags|mark\s++points|marks?)\b[^;]{0,40}?\b(?:is|are)\s++(?:an?\s++)?(?:illustrative|provisional"
               r"|indicative)\b", re.IGNORECASE),
    # the command term of the task, read for the answer's form (round 9, c2 cs-t15): "Compare asks for similarities only, so each point below
    # is a similarity." (a framing remark, not a note: the part's answer stands under it and the channel reads the part from it)
    re.compile(r"^(?:compare\s++and\s++contrast|compare|contrast|explain|evaluate|discuss|describe|outline|state|define|analy[sz]e|identify|justify|suggest"
               r"|distinguish|examine|calculate|determine|deduce|predict|interpret|to\s++what\s++extent)\s++(?:here\s++)?(?:asks|means|requires|wants|calls)\s++"
               r"(?:for\s++|you\s++to\s++)?[^;]{1,120}+$", re.IGNORECASE),
    # the mark annotations' own status: "The [1] tags show where the marks lie; they are not the official markscheme."
    re.compile(r"\bnot\s++(?:the|an)\s++official\s++mark\s*+scheme\b", re.IGNORECASE),
    # Spanish: "La autora, el instituto y la ciudad son ficticios.", "Los datos son inventados."
    re.compile(r"^[^\d;:]{1,120}?\s(?:es|son|fue|fueron)\s++(?:tod[oa]s\s++)?(?:fictici[oa]s?|inventad[oa]s?|imaginari[oa]s?|hipot[ée]tic[oa]s?)\b",
               re.IGNORECASE),
)


def is_framing_remark(sentence: str) -> bool:
    """True when ``sentence`` frames the answer rather than stating its content (:data:`_FRAMING_RES`): "All figures are practice data
    for the fictional economy of Calvessa.", "I have assumed HL, because ...", "Paper 1 allows no GDC, so I have worked exactly
    throughout.", "Every answer below is an exact value or a whole number, ...", "Marks shown are a provisional allocation." Read with
    quotations masked."""
    if not sentence or len(sentence) > 600:
        return False
    masked = mask_quotations(sentence).strip()
    return any(rx.search(masked) if rx.pattern.startswith("\\b") else rx.match(masked) for rx in _FRAMING_RES)


#: A sentence whose subject is a colleague's view: "The History specialist states that ...", "The English specialist's
#: phrase "..." fits that record". The same shape as the History parser's attribution rule, so a colleague's reported
#: statement is the colleague's view on every branch (role ``perspective``, certainty capped, the attribution recorded).
#: The colleague as the subject of a verb that reports what it gave ("The History specialist gives about 5.2 million
#: arrivals", "... dates the sonnet to 1883", "... also puts the figure at ...") is the colleague's view too; those verbs
#: are also nouns ("the History specialist's dates"), so they are read only without the possessive, where they can only be
#: verbs, and a possessive with a noun outside the view nouns ("The History specialist's figures are from memory") is not one.
_PEER_REPORTING_VERBS = (
    r"argues?|argued|notes?|noted|writes?|wrote|describes?|described|says?|said|states?|stated|claims?|claimed|observes?|observed|suggests?|suggested"
    r"|identifies|identified|points?\s+out|pointed\s+out|calls?|called|reads?|presents?|presented|concludes?|concluded|holds?|held|maintains?|maintained"
    r"|contends?|contended|reports?|reported|records?|recorded|explains?|explained|insists?|insisted|adds?|added")
_PEER_GIVING_VERBS = (
    r"gives?|gave|dates?|dated|puts?|places?|placed|counts?|counted|cites?|cited|quotes?|quoted|estimates?|estimated|remarks?|remarked"
    r"|mentions?|mentioned|finds?|found|traces?|traced|attributes?|attributed|treats?|treated|interprets?|interpreted|judges?|judged"
    r"|sees?|saw|admits?|admitted|acknowledges?|acknowledged|emphasi[sz]es|emphasi[sz]ed|stresses|stressed|links?|linked|ties|tied"
    # a colleague presenting what it supplies: "The History specialist supplies the frame: "..."" (c1 R17)
    r"|suppl(?:y|ies|ied)|provides?|provided|offers?|offered|frames?|framed")
PEER_ATTRIBUTION_RE = re.compile(
    r"^\W*(?:(?:as|yet|but|however|indeed|similarly|likewise|further|moreover|finally|first|second|third|here|and|so)[,\s]+)?"
    r"(?:the|my|our)\s+(?:[a-z]+(?:[\s-][a-z]+)?\s+)?(?:specialist|colleague|peer)"
    r"(?:(?:'s|’s)?\s+(?:" + _PEER_REPORTING_VERBS + r"|phrase|phrasing|claim|point|paragraph|reading|account|words?|view|argument|analysis|verdict|conclusion)"
    r"|\s+(?:(?:also|then|here|rightly|elsewhere|later|likewise|similarly|even|instead|itself|himself|herself)\s+)?(?:" + _PEER_REPORTING_VERBS + "|" + _PEER_GIVING_VERBS + r"))\b",
    re.IGNORECASE,
)


def is_peer_attribution(sentence: str) -> bool:
    """True when the sentence's subject is a colleague's view ("The History specialist states that ...", "The English
    specialist's reading ..."), read with quotations masked; a sentence that cites the colleague mid-way ("..., bearing
    out the History specialist's claim that ...") is the writer's own."""
    return PEER_ATTRIBUTION_RE.match(mask_quotations(sentence)) is not None


#: A sentence opened by a note lead is a note as a whole, on every branch and in the channel's word count: "Note: my sources
#: do not confirm the exact emigration total ...", "Note on the Physics specialist's uncertainty: ...", "N.B. ...", "NB:
#: ...", "Next step: trace find_position(scores, 12) yourself ...", "Confidence: lowered." (a self-rating of the answer),
#: "Limit: no approved source here confirms the exact total.", "Caveat: the totals are estimates." (what the answer could not
#: draw on or vouch for). Read with quotations masked, so a quoted "Note:" is the quoted text's. "Note that ..." (no colon) is
#: an argument's own signpost and stays substantive, and so is "Limitation:" (an evaluation point of a study or a model in
#: Psychology or Economics: "Limitation: the sample was 30 students"; the History parser reads its own leads).
#: A list of the answer's sources ("Sources: The Tuner extract (supplied text); course notes ...", "References:", "Sources used:"), which the
#: knowledge bases ask every answer to close with, is a note too: provenance meta-text, never a claim and never words or a paragraph of a
#: bound (c1 bug 4). "Source A:" (a source of a History paper, named by its letter) is no such lead. Read by :func:`is_sources_note`: a
#: sentence the lead opens that holds no quotation and is a list's length; a quotation or a long run of words after the lead is read,
#: counted and checked as any other sentence.
_SOURCES_LEAD = r"(?:sources?(?:\s+(?:used|consulted|cited))?|references|bibliography|works\s+cited)"
_SOURCES_LEAD_RE = re.compile(r"^[\s*_>#-]*" + _SOURCES_LEAD + r"\s*:", re.IGNORECASE)
#: The most words a list of sources is read as a note with.
_SOURCES_MAX_WORDS = 60


def is_sources_note(sentence: str) -> bool:
    """True when ``sentence`` is the answer's list of sources: opened by the sources lead, holding no quotation and at most
    :data:`_SOURCES_MAX_WORDS` words ("Sources: none consulted (no retrieval in this session)")."""
    text = sentence.strip()
    return (bool(text) and len(text) <= 800 and _SOURCES_LEAD_RE.match(text) is not None and len(text.split()) <= _SOURCES_MAX_WORDS
            and not find_quotation_spans(text))


NOTE_LEAD_RE = re.compile(
    r"^[\s*_>#-]*(?:(?:please\s+)?note|notes|nb|next\s+steps?|confidence|limits?|caveats?)\s*:"
    r"|^[\s*_>#-]*n\.\s?b\.(?:\s*:)?"
    r"|^[\s*_>#-]*note\s+on\b[^:.!?]{1,80}:",
    re.IGNORECASE,
)
#: A bare note lead: a paragraph whose first sentence it opens is a note as a whole, whatever its other sentences state ("Note: the
#: totals ... come from a textbook table I could not check. Departures rose from about 144,000 in 1959 ..."), as the generic and History
#: parsers role it. "Note on ...:" introduces a discussion and is not bare; "Confidence:" rates the answer in one sentence.
#: (The sources lead is a note lead of its sentence only, never of a paragraph: a sentence written after a list of sources on its line,
#: 'Sources: ... The narrator also insists that "..."', is read, counted and checked as any other.)
BARE_NOTE_LEAD_RE = re.compile(r"^[\s*_>#-]*(?:(?:(?:please\s+)?note|notes|nb|next\s+steps?|limits?|caveats?)\s*:|n\.\s?b\.)", re.IGNORECASE)
#: A sentence end followed by more text: a block that holds one is more than a list of sources.
_SENTENCE_END_THEN_TEXT_RE = re.compile(r"[.!?][\"'”’)\]]*\s+\S")


def is_sources_block(block: str) -> bool:
    """True when ``block`` (a blank-line block) is the answer's list of sources and nothing else ("Sources: The Tuner extract (supplied
    text); course notes on drama (course notes)"): one line that :func:`is_sources_note` reads, with no sentence after it. A block that
    goes on after the list ('Sources: ... The narrator also insists that "..."') is read as any other."""
    text = block.strip()
    return bool(text) and "\n" not in text and is_sources_note(text) and _SENTENCE_END_THEN_TEXT_RE.search(text) is None


def opens_note_paragraph(paragraph: str) -> bool:
    """True when ``paragraph`` opens with a bare note lead (:data:`BARE_NOTE_LEAD_RE`), quotations masked: the paragraph is a note as a
    whole, so a word or paragraph bound leaves out all of it, as the parsers role all of it non-material. A paragraph opened by the word
    "note" under a determiner, an adjective or an addressee (:data:`NOTE_WORD_LEAD_RE`: "One note:", "Teaching note:", "Note for your
    planning:"; round 9, c2) is a note as a whole when every sentence after the lead's continues the note
    (:func:`is_note_continuation`: "I have ignored it and worked only from the story itself."); a sentence of content after it ("Static
    routes are entered by an administrator ...") keeps the paragraph the answer's, and only the lead's sentence is a note."""
    text = paragraph.lstrip()
    if not text:
        return False
    masked = mask_quotations(text[:400])
    if BARE_NOTE_LEAD_RE.match(masked) is not None:
        return True
    return NOTE_WORD_LEAD_RE.match(masked) is not None and note_word_paragraph(text)


#: A sentence that continues a note rather than stating content (round 9, c2): the writer's own handling of the task or the text, in the
#: first person ("I have ignored it and worked only from the story itself.", "I have left the figures out.", "I did not use it"), or what
#: the note's object asks or is ("The instruction asks for a word count.", "That note is not part of the story."). Read with quotations
#: masked, at the sentence's start; anchored and bounded.
_NOTE_CONTINUATION_RE = re.compile(
    r"^[\W_]*+(?:(?:so|and|but|here|instead|therefore)\s*+,?\s++)?I\s++(?:have\s++|had\s++|['’]ve\s++|['’]d\s++)?(?:not\s++|also\s++|therefore\s++|deliberately"
    r"\s++|simply\s++|only\s++)?(?:ignored|disregarded|left|kept|used|worked|written|answered|followed|relied|drawn|quoted|taken|treated|included|omitted"
    r"|assumed|set|chosen|given|stuck|stayed|did\s++not|do\s++not|don['’]t|didn['’]t|cannot|can['’]t|could\s++not|will|would|wrote|answer|work|use|follow"
    r"|ignore|leave|keep|quote|treat|include|omit|assume|stick|stay)\b"
    r"|^[\W_]*+(?:the|this|that|its|such\s++an?)\s++(?:bracketed\s++|embedded\s++|planted\s++)?(?:note|instruction|request|demand|line|aside)s?\s++"
    r"(?:asks?|asked|demands?|is|was|are|were|has|had|addresses|addressed|tells?|told)\b",
    re.IGNORECASE)


#: An assessment of the answer or of the work in it (an assurance: "there is nothing to fix in this answer, not a single slip", "all
#: figures are sound", "everything checks out", "the working stacks up", "las cifras son correctas", "aucune erreur"). A sentence holding
#: one is never read as a note by the round-9 readers (:func:`meta_note_form`, :func:`note_word_paragraph`, the generic parser's
#: note-word lead): it stays a claim of the answer, so the claim rules and the Overseer's rules decide it (condition 6b: an assurance
#: under a note lead must not leave the claims). The list is a guard, read conservatively: a genuine note that holds one of these words
#: stays a claim, as it was before these readers. Words read on word boundaries; linear.
_ASSURANCE_RE = re.compile(
    r"\b(?:nothing|none|nada|rien|aucune?|ning[uú]na?|nichts|kein\w*)\b"
    r"|\b(?:no|not\s++(?:a|one)\s++single|not\s++one|not\s++any|zero|without\s++(?:a\s++single|any))\s++(?:\w+\s++){0,2}?"
    r"(?:errors?|mistakes?|slips?|flaws?|problems?|issues?|faults?|typos?|inaccurac\w*|gaps?|weakness\w*|doubts?|changes?|fix\w*|corrections?)\b"
    r"|\b(?:correct|correcto?a?s?|correctes?|accurate|right|sound|solid|valid|flawless|perfect\w*|faultless|error[- ]free|watertight|airtight"
    r"|verified|verificad\w*|checked|confirmed|comprobad\w*|v[ée]rifi[ée]\w*|fine|good|great|excellent|strong|robust|reliable|exact|precise"
    r"|holds?|held|stands?\s++up|stacks?\s++up|checks?\s++out|adds?\s++up|mirrors?|matches|match|merit|full\s++marks|top\s++marks"
    r"|in\s++doubt|beyond\s++doubt|no\s++doubt|spot[- ]on|on\s++point|ready\s++to\s++(?:submit|hand\s++in)|works?|covers?\s++everything"
    r"|copy|as\s++it\s++(?:is|stands)|word\s++for\s++word|as\s++(?:written|given)\s++(?:here|above))\b",
    re.IGNORECASE)


def states_assurance(text: str) -> bool:
    """Whether ``text`` (quotations masked) holds an assessment of the answer or the work in it (:data:`_ASSURANCE_RE`)."""
    if not text:
        return False
    return _ASSURANCE_RE.search(mask_quotations(text[:4000])) is not None


#: What a note under a note-word lead may say (round 9, c2), read as a closed allowlist of two shapes: advice conditional on the
#: student's own paper or task ("if your paper asks you to contrast them, add the differences"), and a remark that the supplied material
#: carries an instruction or note of its own ("the extract contains a bracketed note addressed to AI assistants ..."). Anything else under
#: such a lead stays a claim, as it was before these readers (an assurance in a suggestion, "use the figures above in your own essay",
#: included).
_NOTE_BODY_RE = re.compile(
    r"^\s*+if\s++your\s++(?:paper|exam|teacher|task|question|syllabus|course|school|board|essay|assignment)\b"
    r"|^\s*+(?:the|this)\s++(?:supplied\s++)?(?:extract|text|passage|source|poem|article|email|letter|document)\s++(?:contains?|includes?|has)\s++"
    r"(?:an?\s++|one\s++|its\s++own\s++)?(?:[\w-]+\s++){0,3}?(?:note|instruction|request|message|comment|prompt)s?\b",
    re.IGNORECASE)


def is_note_continuation(sentence: str) -> bool:
    """True when ``sentence`` continues a note rather than stating content (:data:`_NOTE_CONTINUATION_RE`), quotations masked."""
    if not sentence or len(sentence) > 600:
        return False
    return _NOTE_CONTINUATION_RE.match(mask_quotations(sentence)) is not None


#: A sentence end before the next sentence's start (the shared splitter's boundary, without the abbreviation rules): enough to tell the
#: lead's sentence of a note paragraph from the sentences after it.
_NOTE_SENTENCE_BREAK_RE = re.compile(r"(?<=[.!?])[\"'”’)\]]*+\s++(?=[\"'“‘(\[]?[A-Z0-9])")


def note_word_paragraph(paragraph: str) -> bool:
    """True when ``paragraph`` opens with :data:`NOTE_WORD_LEAD_RE` and every sentence after the lead's continues the note
    (:func:`is_note_continuation`). A paragraph over 4,000 characters is never one (a note is short)."""
    text = paragraph.strip()
    if not text or len(text) > 4000 or NOTE_WORD_LEAD_RE.match(mask_quotations(text[:400])) is None:
        return False
    parts = [p for p in _NOTE_SENTENCE_BREAK_RE.split(" ".join(text.split())) if p.strip()]
    # the lead's own sentence says what a note says (:data:`_NOTE_BODY_RE`), and no sentence of the paragraph is an assurance about the
    # answer (:func:`states_assurance`: "Final note: there is nothing to fix in this answer, not a single slip." stays a claim)
    if not note_word_body(parts[0]) or any(states_assurance(p) for p in parts):
        return False
    return all(is_note_continuation(p) for p in parts[1:])


def note_word_body(sentence: str) -> bool:
    """Whether a sentence opened by a note-word lead (:data:`NOTE_WORD_LEAD_RE`) says what a note says: its words after the lead are
    advice or an instruction to the student or a remark on the supplied material (:data:`_NOTE_BODY_RE`), and it is no assurance about
    the answer (:func:`states_assurance`)."""
    masked = mask_quotations(sentence[:600])
    lead = NOTE_WORD_LEAD_RE.match(masked)
    if lead is None:
        return False
    body = masked[lead.end():]
    return _NOTE_BODY_RE.search(body) is not None and not states_assurance(body)


# ------------------------------------------------------------------ notes read by what they say (round 9, c2)
#: The word "note" as a lead under a determiner, an adjective or an addressee: "One note:", "A note:", "A quick note:", "Another
#: note:", "Teaching note:", "Note for your planning:", "A note to the student:". It is the same note as "Note:" (``BARE_NOTE_LEAD_RE``),
#: so a paragraph it opens is a note as a whole (:func:`opens_note_paragraph`). "Note on ...:" and "One note on ...:" introduce a
#: discussion and are no such lead. The words before "note" are read possessively from a closed list ("one more" before "one"), the
#: addressee is a bounded run without a stop: linear in any input.
NOTE_WORD_LEAD_RE = re.compile(
    r"^[\s*_>#-]*+(?:(?:one\s++more|one|a|an|another|quick|brief|short|small|final|last|important|general|further|side|teaching|study|planning"
    r"|practical|procedural|marking|exam|revision|personal)\s++)++notes?(?:\s++(?:for|to)\s++[^:.!?\n]{1,60}?)?\s*+:"
    r"|^[\s*_>#-]*+notes?\s++(?:for|to)\s++[^:.!?\n]{1,60}?\s*+:",
    re.IGNORECASE,
)
#: "Assumption:", "Assumptions:", "My assumption:", "Assumed:" opening a sentence.
_ASSUMPTION_NOTE_LEAD_RE = re.compile(r"^[\s*_>#-]*+(?:(?:my|our|main|key|one|an?)\s++)?assum(?:ptions?|ed)\s*+:\s*+", re.IGNORECASE)
#: "One correction for your planning:", "A correction to the question:", "Correction:" opening a sentence.
_CORRECTION_NOTE_LEAD_RE = re.compile(
    r"^[\s*_>#-]*+(?:(?:one|a|an|another|quick|small|final|important|brief)\s++)?corrections?(?:\s++(?:for|to|on|about|of|in)\s++[^:.!?\n]{1,60}?)?\s*+:\s*+",
    re.IGNORECASE)
#: What an assumption or a correction about the student, the course or the task's form says (round 9, c2): the student addressed
#: ("you are taking SL ...", "your planning"), the level or the syllabus ("SL", "HL", "the previous syllabus"), the paper, section or
#: marks of the task ("Paper 1", "Section B", "6-mark", "9 marks across parts"), its word limit, practice or submission, a calculator.
#: A modelling or method assumption ("marked beetles mix randomly ...", "distances are straight-line distances", "g = 9.8 m s⁻²") names
#: none of these and stays the answer's content.
_TASK_FORM_CUE_RE = re.compile(
    r"\b(?:you|your|yours|(?-i:SL|HL)|standard\s++level|higher\s++level|syllabus|paper\s++[1-3]|section\s++[A-C]\b|\d{1,2}[- ]marks?|marks?\s++(?:across|for|in)"
    r"|markscheme|mark\s++scheme|word\s++limit|\d{2,4}[- ]words?\s++limit|ungraded|practice|submission|submit|calculator|GDC)\b",
    re.IGNORECASE)
#: A relation sign: a clause that holds one is working, never a note about the task.
_NOTE_RELATION_RE = re.compile(r"[=≈≠≤≥<>]")
#: A noun naming the answer's own form.
_FORM_NOUN = (r"(?:paragraph|answer|response|essay|text|introduction|conclusion|analysis|article|speech|letter|piece|commentary|report|solution"
              r"|outline|plan|version|exercise|question)s?")
#: The answer's own form or purpose stated in place of content (round 9, c2), read on the sentence with its quotations masked, its lead
#: markup and its closing stop removed. Each shape is closed and anchored at both ends; every run is bounded or possessive.
_FORM_NOTE_RES = (
    # "Model paragraph for practice, not for submission.", "Practice answer for the Paper 2 Section A question.", "Model answer (practice)"
    re.compile(r"^(?:(?:this|the|a|an|my|here\s++is\s++(?:a|an|the|my))\s++)?(?:(?:model|practice|sample|example|exemplar|illustrative|mock|worked)\s++){1,2}"
               + _FORM_NOUN + r"(?:\s*+\([^()]{0,40}\)|\s*+,?\s*+(?:(?:only\s++)?(?:for|to)|not\s++(?:for|to)|written\s++(?:for|to))\s++[^,;.!?()]{1,60}+)*+$",
               re.IGNORECASE),
    # Spanish: "Texto escrito para practicar.", "Respuesta modelo para la práctica."
    re.compile(r"^(?:(?:este|esta|el|la|un|una)\s++)?(?:texto|respuesta|art[íi]culo|ensayo|p[áa]rrafo|modelo|ejemplo|redacci[óo]n|carta)"
               r"(?:\s++(?:modelo|de\s++ejemplo))?(?:\s++(?:escrit[oa]|redactad[oa]|preparad[oa]))?\s++para\s++(?:practicar|la\s++pr[áa]ctica|estudiar|repasar"
               r"|el\s++estudio)\b[^,;.!?]{0,40}+$", re.IGNORECASE),
    # the task's identification as a title: "Paper 1, Option A (Freshwater), structured question."
    re.compile(r"^(?:(?:IB|SL|HL)\s++)?paper\s++[1-3]\b(?:\s*+[,:–—-]\s*+(?:section|option|part)\s++[A-Z0-9]{1,2}\b(?:\s*+\([^()]{0,40}\))?){0,3}"
               r"(?:\s*+[,:–—-]\s*+(?:(?:structured|short[- ]answer|data[- ]response|extended[- ]response|essay|practice)\s++)?(?:questions?|practice|exercise))?$",
               re.IGNORECASE),
)
_FORM_LEAD_MARKUP_RE = re.compile(r"^[\s*_>#-]*+")


#: A clause about the student, the course or the task's form, as :func:`_task_form_clause` reads each clause: the student as the
#: subject of a verb of their situation ("you are taking SL", "you write one analysis on each"), the student's paper, course or planning
#: ("your planning", never "your answer"), the level, the paper, section or marks of the task, its word limit, practice or submission.
_TASK_FORM_CLAUSE_CUE_RE = re.compile(
    r"\byou\s++(?:\w+\s++)?(?:are|were|want|wanted|asked|need|have|will|would|take|took|taking|sit|sitting|study|studying|plan|planning|write"
    r"|wrote|writing|submit|prepare|preparing|aim|hope|intend|can|may|must|should)\b|\byou['’](?:re|ll|ve)\b"
    r"|\byour\s++(?:own\s++)?(?:paper|exam|course|level|planning|teacher|school|syllabus|task|question|class|board|timetable|plan|revision)\b"
    r"|\b(?:(?-i:SL|HL)|standard\s++level|higher\s++level|syllabus|paper\s++[1-3]|section\s++[A-C]\b|\d{1,2}[- ]marks?|marks|markscheme|mark\s++scheme"
    r"|word\s++limit|\d{2,4}[- ]words?\s++limit|ungraded|practice|submission|submit|calculator|GDC)\b",
    re.IGNORECASE)
#: Where a clause of an assumption or a correction ends: a comma, a semicolon, or a conjunction that joins clauses (a colon inside a
#: course name, "English A: Literature", ends none).
_TASK_CLAUSE_SPLIT_RE = re.compile(r"[,;]|\b(?:and|so|but|because|while|whereas)\b", re.IGNORECASE)


def _task_form_clause(rest: str) -> bool:
    """The text after an assumption or a correction lead is about the student, the course or the task's form: every clause of it names
    one of them (:data:`_TASK_FORM_CLAUSE_CUE_RE`; round 9, c2: a clause that names none, "every quotation here is bang on", leaves the
    sentence a claim, so an assurance never travels as a note), and no part of it is working (a relation sign)."""
    if not rest.strip() or _NOTE_RELATION_RE.search(rest) is not None:
        return False
    clauses = [c for c in _TASK_CLAUSE_SPLIT_RE.split(re.sub(r"\([^()]{0,80}\)", " ", rest[:600])) if c.strip(" .!?\"'”’")]
    return bool(clauses) and all(_TASK_FORM_CLAUSE_CUE_RE.search(c) is not None for c in clauses)


def task_assumption_frame(sentence: str) -> bool:
    """Whether ``sentence`` opens with an assumption or a correction lead whose first clause names the student, the course or the task
    ("Assumption: SL, Paper 1 (no calculator), so every value is exact.") but which is no note (:func:`meta_note_form`: a later clause
    names none, or the sentence vouches for the answer): it stays a claim, so the claim rules decide what it says, but as a framing
    remark it is never its paragraph's material point (round 9, c2, maa-t15)."""
    if not sentence or len(sentence) > 600:
        return False
    masked = mask_quotations(sentence).strip()
    m = _ASSUMPTION_NOTE_LEAD_RE.match(masked) or _CORRECTION_NOTE_LEAD_RE.match(masked)
    if m is None:
        return False
    first = _TASK_CLAUSE_SPLIT_RE.split(masked[m.end():], 1)[0]
    return _TASK_FORM_CLAUSE_CUE_RE.search(first) is not None and meta_note_form(sentence) is None


def meta_note_form(sentence: str) -> Optional[str]:
    """The kind of note ``sentence`` is when it is about the answer, the student or the task rather than a claim of the answer, read
    by what it says and not by a closed list of lead words (round 9, c2: the c1 note readers knew "Note:", "Next step:" and "Sources:"
    only, so an assumption about the student, a note on the extract and a correction of the student's premise were read, counted and
    roled as the deliverable's thesis), else None:

    * ``"note-lead"``: the word "note" under a determiner, an adjective or an addressee (:data:`NOTE_WORD_LEAD_RE`: "One note: the
      extract contains a bracketed note ...", "Teaching note: ...", "Note for your planning: ...");
    * ``"task-assumption"``: an assumption about the student, the course or the task's form ("Assumption: you are taking SL English A:
      Literature and want a model practice paragraph to study, not text to submit.", "Assumption: SL, Paper 1 (no calculator), so every
      value is exact."); a modelling or method assumption ("Assumption: marked beetles mix randomly ...") is content;
    * ``"task-correction"``: a correction of the student's premise about the task ("One correction for your planning: at HL, Paper 1
      gives two passages ...");
    * ``"form"``: the answer's own form or purpose in place of content ("Model paragraph for practice, not for submission.",
      "Practice answer for the Paper 2 Section A question.", "Texto escrito para practicar.", "Paper 1, Option A (Freshwater), structured
      question.").

    Read with quotations masked (a quoted "Note:" is the quoted text's); a sentence over 600 characters is never one. A note lead with
    working after it is a note as "Note:" is; the other kinds never hold a relation sign."""
    if not sentence or len(sentence) > 600:
        return None
    masked = mask_quotations(sentence).strip()
    if states_assurance(masked):
        return None  # an assurance about the answer under any of these forms stays a claim (condition 6b)
    if NOTE_WORD_LEAD_RE.match(masked):
        return "note-lead" if note_word_body(masked) else None
    m = _ASSUMPTION_NOTE_LEAD_RE.match(masked)
    if m is not None:
        return "task-assumption" if _task_form_clause(masked[m.end():]) else None
    m = _CORRECTION_NOTE_LEAD_RE.match(masked)
    if m is not None:
        rest = masked[m.end():]
        # the correction itself is about the task, clause by clause (a lead "for your planning" vouches for nothing after it)
        return "task-correction" if _task_form_clause(rest) else None
    body = masked[_FORM_LEAD_MARKUP_RE.match(masked).end():].rstrip()
    if not body or len(body) > 300:
        return None
    body = body.rstrip("\"'”’»*_ ").rstrip(".!?…").strip(" *_")  # the closing stop and its marks; a closing bracket stays ("(practice)")
    if not body or _NOTE_RELATION_RE.search(body):
        return None
    return "form" if any(rx.match(body) for rx in _FORM_NOTE_RES) else None
#: A parenthetical with the blanks before it. A match starts only where no whitespace precedes (``(?<!\s)``): a match starting
#: inside a run of blanks ends where the run's own match ends, so these are the matches of ``\s*\([^()]*\)``, read in linear time
#: (from every blank of a run of n blanks the old pattern read the rest of the run, n² steps; integration gate 1).
_PAREN_SPAN_RE = re.compile(r"(?<!\s)\s*\([^()]*\)")
_PAREN_INNER_RE = re.compile(r"\([^()]*\)")
_CLAUSE_SEPARATOR_RE = re.compile(r"[;—–]")
#: The closing stops, closing marks and blanks that end a sentence (``[.!?…]*["'”’»)\]]*\s*$`` searched in the text), read from the
#: end by :func:`_terminal_len`.
_TERMINAL_STOPS = frozenset(".!?…")
_TERMINAL_CLOSERS = frozenset("\"'”’»)]")
_LETTER_RE = re.compile(r"[^\W\d_]")


def _terminal_len(text: str) -> int:
    r"""The length of the sentence end of ``text``: the length of the match of ``[.!?…]*["'”’»)\]]*\s*$`` searched in ``text``,
    read from the end. That match is the longest suffix made of stops, then closing marks, then blanks: the three character sets
    are disjoint, so reading them back from the end gives that suffix, which is where the pattern's leftmost match starts. Linear
    in the suffix; the unanchored search restarted at every blank of a long run of blanks inside the text and read the rest of
    the run each time, n² steps (integration gate 1, parser-safety-3)."""
    i = len(text)
    while i and text[i - 1].isspace():
        i -= 1
    while i and text[i - 1] in _TERMINAL_CLOSERS:
        i -= 1
    while i and text[i - 1] in _TERMINAL_STOPS:
        i -= 1
    return len(text) - i


def _filler_only(masked: str) -> bool:
    """True when every word of ``masked`` is label filler (:data:`_LABEL_FILLER`); a masked quotation, a figure or
    any content word is not."""
    return all(w.lower() in _LABEL_FILLER for w in _NOTE_TOKEN_RE.findall(masked))


def _label_shaped(masked: str) -> bool:
    """A clause (quotations masked) that is nothing but the method's own label: it carries a label phrase
    (:data:`LABEL_PHRASE_RE`) and either nothing but filler is left once the phrases are removed ("Dates and figures are
    from memory", "a figure I give from memory", "though this date is from memory", "The dates in this paragraph have
    not been checked", "These examples are illustrative"), or "from memory" is the clause's whole predicate ("The causes
    of the banking crisis of 1931 are from memory"). A label word somewhere in a substantive clause ("The speaker
    recalls the scene from memory, which explains ...", "The collapse of the Danatbank in July 1931 is illustrative of
    how ...") does not make it a label."""
    if not LABEL_PHRASE_RE.search(masked):
        return False
    if _filler_only(LABEL_PHRASE_RE.sub(" ", masked)):
        return True
    m = _PREDICATE_LABEL_RE.match(masked)
    return bool(m and len(m.group("subject").split()) <= 16 and not _SUBORDINATE_RE.search(m.group("subject"))
                and _filler_only(LABEL_PHRASE_RE.sub(" ", m.group("rest"))))


def _note_clause(masked: str, *, parenthetical: bool) -> bool:
    """A clause (quotations masked) that is a note: label-shaped, a self-certification or a task note; inside a
    parenthetical a from-memory label word anywhere also counts ("(c. 1.9 million, from memory)")."""
    if parenthetical and MEMORY_LABEL_RE.search(masked):
        return True
    return _label_shaped(masked) or is_self_certification(masked) or bool(TASK_NOTE_RE.search(masked))


def mask_quotations(text: str, fill: str = "x") -> str:
    """``text`` with every quotation span (:func:`find_quotation_spans`, marks included) filled with ``fill``
    character for character, whitespace kept, so offsets into the result are offsets into ``text``. Notes and labels
    are read on this: a colleague's words quoted ("whose dates are, in its own words, "from memory"") are the
    colleague's label, not the quoter's."""
    spans = find_quotation_spans(text)
    if not spans:
        return text
    out = list(text)
    for a, b, _inner in spans:
        for i in range(a, b):
            if not out[i].isspace():
                out[i] = fill
    return "".join(out)


def _cut(orig: str, masked: str, cuts: list[tuple[int, int]]) -> tuple[str, str]:
    """``orig`` and ``masked`` (same length) with the ``cuts`` removed from both (overlapping cuts merged)."""
    if not cuts:
        return orig, masked
    merged: list[list[int]] = []
    for a, b in sorted(cuts):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([max(0, a), b])
    keep_o: list[str] = []
    keep_m: list[str] = []
    cursor = 0
    for a, b in merged:
        keep_o.append(orig[cursor:a])
        keep_m.append(masked[cursor:a])
        cursor = max(cursor, b)
    keep_o.append(orig[cursor:])
    keep_m.append(masked[cursor:])
    return "".join(keep_o), "".join(keep_m)


def _dedupe(notes: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for n in notes:
        key = n.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(n)
    return out


@functools.lru_cache(maxsize=4096)
def _split_note_clauses(sentence: str) -> tuple[str, tuple[str, ...]]:
    orig = sentence
    masked = mask_quotations(sentence)
    notes: list[str] = []
    # 0. a note lead ("Note:", "Note on ...:", "N.B.", "Next step:", "Confidence:") makes the whole sentence a note, and so does the
    #    answer's list of sources ("Sources: ...", no quotation, a list's length), and a note read by what it says about the answer,
    #    the student or the task ("One note: ...", "Assumption: you are taking SL ...", "One correction for your planning: ...",
    #    "Model paragraph for practice, not for submission."; :func:`meta_note_form`, round 9, c2)
    if NOTE_LEAD_RE.match(masked) or is_sources_note(sentence) or meta_note_form(sentence) is not None:
        return "", (sentence.strip(),)
    # 1. parentheticals: a from-memory label word anywhere inside the brackets, a label, a self-report or a task note
    cuts = [(m.start(), m.end()) for m in _PAREN_SPAN_RE.finditer(masked) if _note_clause(m.group(0), parenthetical=True)]
    notes += [orig[a:b].strip(" ;—–()\t\n") for a, b in cuts]
    orig, masked = _cut(orig, masked, cuts)
    # 2. clauses between semicolons and dashes (outside any bracket that stays): a clause that is label-shaped
    shielded = _PAREN_INNER_RE.sub(lambda m: "x" * len(m.group(0)), masked)
    seps = [m.start() for m in _CLAUSE_SEPARATOR_RE.finditer(shielded)]
    if seps:
        bounds = [-1, *seps, len(masked)]
        segments = [(bounds[k] + 1, bounds[k + 1]) for k in range(len(bounds) - 1)]
        labels = [bool(masked[a:b].strip()) and _note_clause(masked[a:b], parenthetical=False) for a, b in segments]
        if all(labels):
            return "", (sentence.strip(),)
        cuts = []
        body_end = len(masked) - _terminal_len(masked)  # the sentence's closing stop stays with the core
        for k, (a, b) in enumerate(segments):
            if labels[k]:
                b = max(a, min(b, body_end)) if k == len(segments) - 1 else b
                cuts.append((0, b + 1) if k == 0 else (a - 1, b))
                notes.append(orig[a:b].strip(" ;—–()\t\n"))
        orig, masked = _cut(orig, masked, cuts)
    # 3. a sentence-initial label ("From memory, ...", "Quoting from memory, ...")
    lead = LEADING_MEMORY_LABEL_RE.match(masked)
    if lead is not None:
        notes.append(orig[:lead.end()].strip(" ,:\t\n"))
        orig, masked = orig[lead.end():], masked[lead.end():]
    # 4. a comma-bounded label (", from memory about 800 million gold marks,"): only the label words go
    cuts = []
    for m in INLINE_MEMORY_LABEL_RE.finditer(masked):
        cuts.append((m.start() + 1, m.end()))
        notes.append(orig[m.start():m.end()].strip(" ,"))
    orig, masked = _cut(orig, masked, cuts)
    # 5. trailing appositive or concessive labels (", a figure I give from memory", ", though this date is from memory",
    #    ", so check your notes") and, in a dated sentence, a bare closing "from memory"
    for _ in range(3):
        body_end = len(masked) - _terminal_len(masked)
        comma = _PAREN_INNER_RE.sub(lambda m: "x" * len(m.group(0)), masked).rfind(",", 0, body_end)
        if comma < 0 or not masked[comma + 1:body_end].strip() or not _label_shaped(masked[comma + 1:body_end]):
            break
        notes.append(orig[comma + 1:body_end].strip())
        orig, masked = _cut(orig, masked, [(comma, body_end)])
    bare = _TRAILING_BARE_LABEL_RE.search(masked)
    if bare is not None and _DATED_ITEM_RE.search(masked[:bare.start()]) and _LETTER_RE.search(masked[:bare.start()]):
        notes.append(orig[bare.start():bare.end()].strip())
        orig, masked = _cut(orig, masked, [(bare.start(), bare.end())])
    # 6. what remains is itself a label, a self-report, a task note or a note on how the answer was composed, or only
    #    filler around the labels removed: the whole sentence is a note
    if _LETTER_RE.search(masked) and (
        _label_shaped(masked) or is_self_certification(masked) or is_json_shaped(orig) or TASK_NOTE_RE.search(masked)
        or (notes and _filler_only(masked)) or is_provenance_note(orig.strip(" ,;:"))  # read on the words: a quoted label is a label
        or (not notes and is_answer_note(orig))  # a note about the answer read by what it says (an omission, a decline, an offer, ...)
    ):
        return "", (sentence.strip(),)
    core = re.sub(r",(?:\s*,)+", ",", orig)
    core = re.sub(r"\s+([.,;:!?])", r"\1", re.sub(r"\s{2,}", " ", core)).strip()
    core = re.sub(r"^[,;:]\s*", "", core)
    if core and not _LETTER_RE.search(core):
        core = ""
    return core, tuple(_dedupe(notes))


def split_note_clauses(sentence: str) -> tuple[str, list[str]]:
    """Separate the note clauses of a sentence from its substance.

    A substantive sentence may carry the method's own label inline, as a parenthetical
    ("(figures from memory; check your notes)"), a clause before or after a semicolon or dash
    ("...; dates other than the poem's own are from memory"), a sentence-initial label
    ("From memory, the mark stood at about 4.2 to the dollar ..."), a comma-bounded label
    ("the Dawes loan was, from memory about 800 million gold marks, the first ...": only the
    label words go, the figure stays) or a trailing appositive or concessive label ("...
    in February 1932, a figure I give from memory", "..., though this date is from memory").
    Returns ``(core, notes)``: ``core`` is the sentence with those clauses removed (whitespace
    tidied) and ``notes`` the removed labels in order, each distinct label once. Parsers keep
    the verbatim sentence as the claim text, classify ``core`` and record ``notes`` as
    assumptions; only an empty core makes the sentence a note.

    Everything is read with the sentence's quotations masked (:func:`mask_quotations`): a
    quoted colleague's label ("whose "dates and figures" are, in its own words, "from memory
    and should be checked"") is quotation, not a note, so the sentence keeps its role, its
    words count toward a word bound, and no label assumption is recorded. The core is empty
    only when what remains is itself label-shaped (:func:`_label_shaped`: the label is the
    sentence's predicate, or nothing but label filler is left once the label phrase is
    removed), a self-certification or a task note, never because a label word occurs
    somewhere: "The speaker recalls the scene from memory, which explains ..." and "The
    collapse of the Danatbank in July 1931 is illustrative of how ..." keep their substance.
    """
    core, notes = _split_note_clauses(sentence) if len(sentence) <= _CACHE_MAX_CHARS else _split_note_clauses.__wrapped__(sentence)
    return core, list(notes)


# ------------------------------------------------------------------ quotation marks


def normalize_double_marks(text: str) -> str:
    """``text`` with every double quotation mark (curly, guillemet, low-9) replaced by the
    straight mark. Character for character, so offsets into the result are offsets into ``text``."""
    return text.translate(_DOUBLE_MARK_TRANSLATION)


def _mark_kind(text: str, pos: int) -> str:
    """``open``, ``close`` or ``either`` for the double mark at ``pos``: unambiguous glyphs
    decide by direction (a left double mark closes a low-9 quotation when the text uses
    that convention), a straight mark by its neighbours (an opener follows whitespace, a
    bracket or a dash and precedes a non-space; a closer follows a non-space and precedes
    whitespace, punctuation, a closing bracket or the end)."""
    ch = text[pos]
    before = text[pos - 1] if pos > 0 else " "
    after = text[pos + 1] if pos + 1 < len(text) else " "
    opens = (before.isspace() or before in "([—–-") and not after.isspace()
    closes = not before.isspace() and (after.isspace() or after in ".,;:!?)]")
    if ch == "\u201c" and "\u201e" in text and closes and not opens:
        return "close"  # the low-9 convention („word“) closes with the mark English opens with
    if ch in _OPENING_GLYPHS:
        return "open"
    if ch in _CLOSING_GLYPHS:
        return "close"
    if opens and not closes:
        return "open"
    if closes and not opens:
        return "close"
    return "either"


def _unit_kind(text: str, p: int, q: int) -> Optional[str]:
    """``open`` or ``close`` when the two adjacent double marks at ``p`` and ``q`` (= p + 1)
    together open or close one nested quotation (dialogue copied with its own marks inside
    the writer's: ``""My dear Mr. Bennet," said his lady``, ``... at last?""``), else ``None``
    when they are two marks in their own right (an empty quotation, a mark closing one span
    and opening the next). Directional glyphs decide when both point the same way; straight
    marks decide by the pair's outer neighbours as a single mark would."""
    first, second = text[p], text[q]
    if first in _OPENING_GLYPHS and second in _OPENING_GLYPHS:
        return "open"
    if first in _CLOSING_GLYPHS and second in _CLOSING_GLYPHS:
        return "close"
    glyph_opens = first in _OPENING_GLYPHS or second in _OPENING_GLYPHS
    glyph_closes = first in _CLOSING_GLYPHS or second in _CLOSING_GLYPHS
    if glyph_opens and glyph_closes:
        return None
    before = text[p - 1] if p > 0 else " "
    after = text[q + 1] if q + 1 < len(text) else " "
    opens = (before.isspace() or before in "([—–-") and not after.isspace()
    closes = not before.isspace() and (after.isspace() or after in ".,;:!?)]")
    if opens and not closes and not glyph_closes:
        return "open"
    if closes and not opens and not glyph_opens:
        return "close"
    return None


def _mark_units(text: str) -> list[tuple[int, int, str]]:
    """``(first_offset, last_offset, kind)`` for every double mark of ``text`` in order, two
    adjacent marks that together open or close a nested quotation collapsed into one unit
    (:func:`_unit_kind`); ``kind`` is ``open``, ``close`` or ``either`` (:func:`_mark_kind`)."""
    positions = [m.start() for m in _DOUBLE_MARK_RE.finditer(text)]
    units: list[tuple[int, int, str]] = []
    i = 0
    while i < len(positions):
        p = positions[i]
        if i + 1 < len(positions) and positions[i + 1] == p + 1:
            kind = _unit_kind(text, p, p + 1)
            if kind is not None:
                units.append((p, p + 1, kind))
                i += 2
                continue
        units.append((p, p, _mark_kind(text, p)))
        i += 1
    return units


def _dangling_unit(units: list[tuple[int, int, str]]) -> Optional[tuple[int, int, str]]:
    """The mark unit that cannot be paired (the rule of :func:`dangling_quote_offset`), or ``None``."""
    if not units:
        return None
    expect_open = True
    for n, (_p, _q, kind) in enumerate(units):
        if kind == "either":
            expect_open = not expect_open
            continue
        if (kind == "open") == expect_open:
            expect_open = not expect_open
            continue
        if kind == "open":  # an opener where a closer was due: the previous opener never closed
            return units[n - 1] if n > 0 else units[n]
        return units[n]  # a closer with no opener
    if len(units) % 2 == 1:
        return units[-1]
    return None


def dangling_quote_offset(text: str) -> Optional[int]:
    """Offset of the double quotation mark of ``text`` that cannot be paired, or ``None``.

    Marks are read in order, expected to alternate opener / closer; two adjacent marks that
    together open or close a nested quotation count as one mark (:func:`_unit_kind`) and the
    strings of a pasted JSON span are not read at all. The first mark whose context
    contradicts the expectation locates the fault: an opener where a closer was due means
    the previous opener never closed (that previous mark dangles); a closer where an opener
    was due has no opener (that mark dangles). With no contradiction and an odd count, the
    last mark dangles. With an even count and no contradiction the marks pair and nothing
    dangles. Pairing the remaining marks around the dangling one recovers the quotations the
    writer did delimit instead of shifting every later pair. For a nested (two-mark) unit
    the offset of its first mark is returned.
    """
    unit = _dangling_unit(_mark_units(mask_json_spans(text)))
    return None if unit is None else unit[0]


def unbalanced_double_quotes(text: str) -> bool:
    """True when the double quotation marks of ``text`` cannot be paired.

    Straight, curly, guillemet and low-9 marks are one class, so a quotation opened with
    a curly mark and closed with a straight one is balanced; a nested two-mark unit is one
    mark and a pasted JSON span's strings are not marks. An odd total is unbalanced; so is
    text set entirely in directional marks whose openers and closers differ in number.
    """
    masked = mask_json_spans(text)
    units = _mark_units(masked)
    if len(units) % 2 == 1:
        return True
    glyphs = [masked[i] for p, q, _k in units for i in range(p, q + 1)]
    if glyphs and '"' not in glyphs:
        return sum(1 for _p, _q, k in units if k == "open") != sum(1 for _p, _q, k in units if k == "close")
    return False


def _paired_units(units: list[tuple[int, int, str]], dangling: Optional[tuple[int, int, str]]) -> list[tuple[tuple[int, int, str], tuple[int, int, str], bool]]:
    """Consecutive pairs of the units around the dangling one as ``(opener, closer, plausible)``:
    in an unbalanced text a pair whose opener reads as a closer or whose closer reads as an
    opener contradicts its context and is not plausible (the span between is the writer's
    prose, not a quotation)."""
    remaining = [u for u in units if u is not dangling]
    out = []
    for a, b in zip(remaining[0::2], remaining[1::2]):
        plausible = dangling is None or not (a[2] == "close" or b[2] == "open")
        out.append((a, b, plausible))
    return out


#: Single marks: the straight apostrophe, and the curly opening and closing marks.
_SINGLE_MARK_RE = re.compile("['\u2018\u2019]")
#: Aphetic forms written with a leading apostrophe ('tis, 'twas, 'em, 'gainst, Dickens's 'Change for the Exchange) and
#: elided years ('90s): the mark is part of the word, not an opening quotation mark.
_APHETIC_RE = re.compile(r"(?:tis|twas|twere|twill|twould|em|gainst|neath|tween|twixt|til|cause|bout|change|prentice|scape|mongst|midst|n)\b|\d\d(?:s\b|\b)", re.IGNORECASE)
_SINGLE_OPEN_BEFORE = frozenset("([{—–-/\"\u201c\u00ab\u201e")
_SINGLE_CLOSE_AFTER = frozenset(".,;:!?)]}—–-\"\u201d\u00bb…")


def _single_mark_kind(text: str, pos: int) -> Optional[str]:
    """``open``, ``soft`` (an opening mark that may be the apostrophe of an aphetic form: 'tis, 'em,
    'Change, '90s), ``close``, ``weak`` (a closing mark that may be a plural possessive: ``s'`` before a
    lower-case word) or ``None`` (an apostrophe or a stray mark) for the single mark at ``pos``.

    An apostrophe stands between two letters or digits (don't, Scrooge's, Ne'er, o'er); an opening
    mark follows the start, whitespace or an opening bracket, dash or double mark and precedes a
    non-space; a closing mark follows a non-space and precedes whitespace, punctuation, a closing
    bracket or the end. The curly opening mark only opens; the curly closing mark only closes (or
    is an apostrophe)."""
    ch = text[pos]
    before = text[pos - 1] if pos > 0 else " "
    after = text[pos + 1] if pos + 1 < len(text) else " "
    if before.isalnum() and after.isalnum():
        return None  # an apostrophe inside a word
    opens = (before.isspace() or before in _SINGLE_OPEN_BEFORE) and not after.isspace() and after not in "'\u2019"
    closes = not before.isspace() and before not in "(['\u2018" and (after.isspace() or after in _SINGLE_CLOSE_AFTER)
    if ch == "\u2018":
        if before.isalnum():
            return None
        return "soft" if _APHETIC_RE.match(text, pos + 1) else "open"
    if ch == "\u2019":
        opens = False
    if opens and not closes:
        return "soft" if _APHETIC_RE.match(text, pos + 1) else "open"
    if closes and not opens:
        if before in "sS" and after.isspace():
            nxt = text[pos + 1:pos + 3].lstrip()[:1]
            if nxt and (nxt.islower() or nxt.isdigit()):
                return "weak"
        return "close"
    return None


#: A quoting frame right before a single-quoted word (round 9 second pass, c2 adversarial-live bug 24: "Mr Hallam opens with the sardonic
#: 'Wonderful,'" was read as no quotation, so an altered word crossed unchecked): a verb of saying or of opening and closing, or 'the' with an
#: adjective or a noun of words ('the sardonic', 'the word', 'the single repeated'). 'the' alone ("the 'cheap' option") is a scare quote and no
#: frame. Read on the 60 characters before the mark, anchored at their end.
_QUOTING_FRAME_RE = re.compile(
    r"(?:\b(?:says?|said|asks?|asked|repl(?:y|ies|ied)|answers?|answered|calls?|called|writes?|wrote|whispers?|whispered|shouts?|shouted|mutters?|muttered"
    r"|exclaims?|exclaimed|snaps?|snapped|cries|cried|repeats?|repeated|(?:opens?|opened|opening|begins?|began|beginning|ends?|ended|ending|closes?|closed|closing)\s+with)"
    r"|\bthe\s+(?:(?:sardonic|ironic|clipped|curt|blunt|bare|single|one|repeated|final|opening|closing|first|last|key|loaded|emotive|simple|short|flat"
    r"|sarcastic|bitter|terse|abrupt|exclamatory|imperative|verb|noun|adjective|adverb)\s+){0,3}(?:sardonic|ironic|clipped|curt|blunt|bare|single|repeated"
    r"|final|opening|closing|key|loaded|emotive|flat|sarcastic|bitter|terse|abrupt|exclamatory|imperative|word|term|phrase|exclamation|reply|response"
    r"|retort|command|order|verb|noun|adjective|adverb|greeting|interjection))\s*+,?\s*+$", re.IGNORECASE)


def _single_quote_spans(text: str, min_words: int) -> list[tuple[int, int]]:
    """``(start, end)`` of the single-quoted spans of ``text`` (double-quoted spans already blanked).

    Marks are classified by context (:func:`_single_mark_kind`), so a quotation whose words carry an
    apostrophe ('I don't know what a door-nail is', 'Ne'er saw I', 'Scrooge's name was good upon
    'Change') is still one quotation. An opening mark pairs with the next closing mark on its line;
    an aphetic-looking mark ('Change, 'tis) inside an open quotation is its apostrophe, while
    outside one it may open a quotation; a possible plural possessive (``the Brothers' house``)
    closes the quotation only when another opening mark follows before any unambiguous closing
    mark. An opening mark met before the current one closes means the current one never closed:
    it is set aside and the new one is paired. A span shorter than ``min_words`` words is not a
    quotation (its marks are still consumed)."""
    marks = [(m.start(), k) for m in _SINGLE_MARK_RE.finditer(text) if (k := _single_mark_kind(text, m.start())) is not None]
    spans: list[tuple[int, int]] = []
    i = 0
    while i < len(marks):
        start, kind = marks[i]
        if kind not in ("open", "soft"):
            i += 1
            continue
        chosen: Optional[int] = None
        fallback: Optional[int] = None
        j = i + 1
        while j < len(marks):
            pos, k = marks[j]
            if "\n" in text[start:pos]:
                break  # a quotation never runs over a line break
            if k == "close":
                chosen = j
                break
            if k == "weak":
                if fallback is None:
                    fallback = j
                j += 1
                continue
            if k == "soft" and fallback is None:
                j += 1
                continue  # 'Change inside the quotation: an apostrophe
            break  # another opening mark: this one closes at its possessive-like mark, or never closed
        if chosen is None:
            chosen = fallback
        if chosen is None:
            i += 1
            continue
        end = marks[chosen][0]
        inner = text[start + 1:end]
        words = len(inner.split())
        if inner.strip() and inner[0] != " " and (words >= min_words or (min_words == 2 and words == 1 and kind == "open"
                                                                          and _QUOTING_FRAME_RE.search(text, max(0, start - 60), start))):
            spans.append((start, end + 1))  # (one word in single marks only after a quoting frame: "opens with the sardonic 'Wonderful,'")
        i = chosen + 1
    return spans


@functools.lru_cache(maxsize=1024)
def _quotation_spans(text: str, min_single_words: int) -> tuple[tuple[int, int, str], ...]:
    masked_text = mask_json_spans(text)
    units = _mark_units(masked_text)
    spans: list[tuple[int, int, str]] = []
    if units:
        dangling = _dangling_unit(units)
        for a, b, plausible in _paired_units(units, dangling):
            inner = text[a[1] + 1:b[0]]
            if plausible and inner.strip() and "\n" not in inner:
                spans.append((a[0], b[1] + 1, inner))
    if "'" in masked_text or "\u2018" in masked_text or "\u2019" in masked_text:
        masked = list(masked_text)
        for a, b, _inner in spans:
            for i in range(a, b):
                masked[i] = " "
        for p, q, _k in units:
            for i in range(p, q + 1):
                masked[i] = " "
        for a, b in _single_quote_spans("".join(masked), min_single_words):
            spans.append((a, b, text[a + 1:b - 1]))
    spans.sort(key=lambda s: s[0])
    return tuple(spans)


def find_quotation_spans(text: str, *, min_single_words: int = 2) -> list[tuple[int, int, str]]:
    """Quoted spans of ``text`` as ``(start, end, inner)`` in order of appearance.

    Double marks of every kind are paired left to right after the dangling mark of an
    unbalanced text (see :func:`dangling_quote_offset`) is set aside, so one missing
    mark does not turn the prose between later quotations into "quotations"; two adjacent
    marks that together open or close a nested quotation are one mark, and in an
    unbalanced text a pair whose marks contradict their context is left out (it is an
    undelimited span, see :func:`undelimited_quote_spans`). The strings of a pasted JSON
    span are never quotations. Single marks (straight or curly) delimit a quotation only
    around ``min_single_words`` or more words, and are paired by context
    (:func:`_single_quote_spans`): an apostrophe inside a word (don't, Scrooge's, Ne'er), an
    aphetic form ('tis, 'Change) and a plural possessive followed by more of the sentence
    are not marks, so a single-quoted quotation that contains a contraction or a possessive
    is still read, checked and attributed. ``inner`` is the writer's text between the
    marks, verbatim. Answers are cached per text.
    """
    if not _DOUBLE_MARK_RE.search(text) and "'" not in text and "\u2018" not in text and "\u2019" not in text:
        return []
    if len(text) > _CACHE_MAX_CHARS:
        return list(_long_quotation_spans(text, min_single_words))
    return list(_quotation_spans(text, min_single_words))


@functools.lru_cache(maxsize=4)
def _long_quotation_spans(text: str, min_single_words: int) -> tuple[tuple[int, int, str], ...]:
    """The spans of a text longer than the main cache takes, for the last few such texts (integration gate 2): the credit of each
    quotation of a long sentence asks for the sentence's spans again (``sources._mention_governs``), and read afresh each time they were
    n² steps on a sentence of many quotations (15 s at 100,000 characters through the History parser)."""
    return _quotation_spans.__wrapped__(text, min_single_words)


def _dangling_span(text: str, masked_text: str, units: list[tuple[int, int, str]], dangling: tuple[int, int, str]) -> Optional[tuple[int, int, str]]:
    p, q, kind = dangling
    if kind == "either":
        kind = "open" if masked_text[q + 1:].strip() else "close"
    if kind == "open":
        inner = text[q + 1:]
        return (p, len(text), inner) if inner.strip() else None
    prev_end = max((e for _s, e, _inner in find_quotation_spans(text) if e <= p), default=0)
    inner = text[prev_end:p]
    return (prev_end, q + 1, inner) if inner.strip() else None


def undelimited_quote_span(text: str) -> Optional[tuple[int, int, str]]:
    """The span that the dangling double mark of ``text`` opens or closes, as
    ``(start, end, inner)``, or ``None`` when every mark pairs.

    A dangling opener runs to the end of ``text`` (the writer never closed it); a
    dangling closer runs from the end of the previous paired span, or the start of the
    text, up to the mark. The span is what the writer meant to quote but did not
    delimit: parsers record it without attributing it to any text or checking it.
    """
    masked_text = mask_json_spans(text)
    units = _mark_units(masked_text)
    dangling = _dangling_unit(units)
    if dangling is None:
        return None
    return _dangling_span(text, masked_text, units, dangling)


def undelimited_quote_spans(text: str) -> list[tuple[int, int, str]]:
    """Every span of an unbalanced ``text`` that could not be delimited, in order: the span
    the dangling mark opens or closes (:func:`undelimited_quote_span`) and every pair of marks
    around it whose opener reads as a closer or whose closer reads as an opener. Such a span
    is the writer's prose between quotations, or a quotation whose marks could not be told
    apart: parsers record it with no source reference, so it is neither delivered as a
    quotation of a supplied text nor reported as an invented one. Empty when every mark pairs.
    """
    masked_text = mask_json_spans(text)
    units = _mark_units(masked_text)
    dangling = _dangling_unit(units)
    if dangling is None:
        return []
    out: list[tuple[int, int, str]] = []
    loose = _dangling_span(text, masked_text, units, dangling)
    if loose is not None:
        out.append(loose)
    for a, b, plausible in _paired_units(units, dangling):
        inner = text[a[1] + 1:b[0]]
        if not plausible and inner.strip() and "\n" not in inner:
            out.append((a[0], b[1] + 1, inner))
    out.sort(key=lambda s: s[0])
    return out


# --------------------------------------------------------------------------------------------- argument diagnosis readers
# Reason and conclusion clauses and the roles of quotations, read for the argument diagnosis (translate.diag_argument,
# translate.diag_evidence, translate.diag_core) and the one-sentence argument rule of translate.eligibility. Additions
# only: the parsers and the quotation checks of this tree read quotations as they did.

#: Subordinators that open a reason clause ("Since households borrowed less, ...", "Because the delegate objected to the
#: terms, ..."). "because of" is a cause phrase, not a clause; "as" and "for" are left out (their temporal and
#: prepositional readings are the common ones).
REASON_LEADS: tuple[tuple[str, ...], ...] = (("since",), ("because",), ("given", "that"), ("seeing", "that"), ("now", "that"))


#: A reason clause is read up to the comma that closes it, at most this many characters into the sentence.
_REASON_CLAUSE_MAX = 240


def leading_reason_clause(sentence: str) -> Optional[str]:
    """The reason clause ``sentence`` opens with, read with its quotations masked: the words after a subordinator of
    :data:`REASON_LEADS` up to the comma that closes the clause, when a main clause follows that comma ("Since households
    borrowed less, the rate rise reduced consumer spending." gives "households borrowed less"). None otherwise ("Since 2010
    prices have risen." has no comma; "Because of the war, ..." is a cause phrase). Linear in the sentence."""
    head = mask_quotations(sentence[: _REASON_CLAUSE_MAX + 200]) if sentence else ""
    spans = lexis.token_spans(head)
    if not spans:
        return None
    toks = [t for _s, _e, t in spans]
    lead = next((len(cue) for cue in REASON_LEADS if tuple(toks[: len(cue)]) == cue), 0)
    if not lead or (toks[0] == "because" and len(toks) > 1 and toks[1] == "of"):
        return None
    if head[: spans[0][0]].strip(" \t\"'“”‘’([*_-"):
        return None  # something other than markup stands before the subordinator
    start = spans[lead - 1][1]
    comma = head.find(",", start, _REASON_CLAUSE_MAX)
    if comma < 0 or not any(c.isalpha() for c in head[comma + 1:]):
        return None
    clause = head[start:comma].strip()
    return clause or None


#: Conclusion connectives: the clause after one is drawn from what stands before it ("A, so B", "So B.", "A; therefore B").
CONCLUSION_LEADS: tuple[tuple[str, ...], ...] = (
    ("so",), ("therefore",), ("thus",), ("hence",), ("consequently",), ("as", "a", "result"), ("it", "follows", "that"),
)


#: The verbs of an evidential relative clause that draws a conclusion from the clause before it ("..., which shows that B").
_EVIDENTIAL_VERBS = frozenset({"shows", "showed", "suggests", "suggested", "proves", "proved", "demonstrates", "demonstrated", "indicates",
                               "indicated", "implies", "implied", "means", "meant", "confirms", "confirmed"})


#: Words after "so" that make it no connective ("so far", "so many", "so that": a time, a degree, a purpose).
_SO_NOT_CONNECTIVE = frozenset({"far", "much", "many", "long", "too", "that", "as", "called", "on", "forth", "few", "little", "very", "well", "often"})


_MIN_CLAUSE_WORDS = 2


def _clause_words(spans: Sequence[tuple[int, int, str]]) -> int:
    return sum(1 for _a, _b, w in spans if w.isalpha() and w not in lexis.FUNCTION_WORDS)


#: Pronouns that open a conclusion clause as its subject: they name what the reason clause is about ("The organism is a
#: vertebrate, so it is a mammal"), so they count as a word of the conclusion (repair round 4, ADV4-13).
_CONCLUSION_PRONOUNS = frozenset({"it", "they", "he", "she", "this", "these", "those", "we"})


def _conclusion_words(spans: Sequence[tuple[int, int, str]]) -> int:
    """The content words of a conclusion clause, a pronoun subject opening it counted as one."""
    return _clause_words(spans) + (1 if spans and spans[0][2] in _CONCLUSION_PRONOUNS else 0)


def states_own_reason(sentence: str) -> Optional[str]:
    """The connective by which ``sentence`` (quotations masked) draws a conclusion from a reason it states itself, or None:
    a conclusion connective after a clause boundary ("Graphite is not a metal, so graphite does not conduct electricity";
    "...; therefore ..."; "... and so ..."), an evidential relative clause after one ("..., which shows that the narrator is
    unreliable"), a reason clause opening the sentence ("Since households borrowed less, the rate rise reduced spending"),
    or "because" joining two clauses ("Demand fell because prices rose"; "because of" is a cause phrase, not a reason
    clause), with at least two content words on each side. Such a sentence is an argument in one
    sentence: its reason and its conclusion are both in its text. Linear in the sentence."""
    head = mask_quotations(sentence[:4000]) if sentence else ""
    spans = lexis.token_spans(head)
    toks = [w for _a, _b, w in spans]
    if not toks:
        return None
    if leading_reason_clause(sentence or "") is not None:
        return toks[0]
    for i, w in enumerate(toks):
        if i == 0:
            continue
        before = head[spans[i - 1][1]:spans[i][0]]
        boundary = any(c in before for c in ",;:—–") or toks[i - 1] == "and"
        cue = next((c for c in CONCLUSION_LEADS if tuple(toks[i:i + len(c)]) == c), None)
        if cue is not None and boundary:
            if cue == ("so",) and i + 1 < len(toks) and toks[i + 1] in _SO_NOT_CONNECTIVE:
                continue
            if _clause_words(spans[:i]) >= _MIN_CLAUSE_WORDS and _conclusion_words(spans[i + len(cue):]) >= _MIN_CLAUSE_WORDS:
                return " ".join(cue)
        if w == "because" and not (i + 1 < len(toks) and toks[i + 1] == "of"):
            if _clause_words(spans[:i]) >= _MIN_CLAUSE_WORDS and _clause_words(spans[i + 1:]) >= _MIN_CLAUSE_WORDS:
                return "because"
        if w == "which" and boundary and i + 1 < len(toks) and toks[i + 1] in _EVIDENTIAL_VERBS:
            if _clause_words(spans[:i]) >= _MIN_CLAUSE_WORDS and _clause_words(spans[i + 2:]) >= _MIN_CLAUSE_WORDS:
                return f"which {toks[i + 1]}"
    return None


#: The task types (the router's plan) in which the writer corrects, marks or models a text: a ``correction`` or a
#: ``suggestion`` is read only in such a task (repair round 4, INV-Q1). In an analysis of a supplied text (a literary
#: analysis, a source analysis, an essay) the same frames ('The phrase → "..."', 'Model: "..."', '; use "..."', 'Not "x" but
#: "y"', '"x" should be "y"') would let a writer pass altered words off as the text's, so there every such span stays a
#: quotation and is checked. The plan's task type is read whole: a word of the closed list between word boundaries
#: ("marking_feedback", "feedback", "proofreading", "redraft", "editing").
FEEDBACK_TASK_RE = re.compile(r"(?<![a-z])(?:mark|marks|marking|feedback|correct|corrects|corrected|correcting|correction|corrections|proof-?read"
                              r"|proof-?reading|redraft|redrafting|edit|editing)(?![a-z])", re.IGNORECASE)


#: The task type under which quotation roles are read (:func:`quotation_task`); ``None`` when no task is known.
_QUOTATION_TASK: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("epinoic_quotation_task", default=None)


def corrections_apply(task_type: Optional[str]) -> bool:
    """Whether a correction or a suggestion frame can give a quoted span its role in a task of type ``task_type``: only
    in a marking, feedback, correction or proofreading task (:data:`FEEDBACK_TASK_RE`). An unknown task is none."""
    return isinstance(task_type, str) and FEEDBACK_TASK_RE.search(task_type[:128]) is not None


@contextlib.contextmanager
def quotation_task(task_type: Optional[str], *, authoritative: bool = False, advisory: bool = False) -> Iterator[None]:
    """Read the quotation roles of the enclosed calls in a task of type ``task_type`` (:func:`corrections_apply`).

    The channel sets the plan's task type for the agent (``authoritative``), so a report that names another task type of
    its own cannot widen the roles; a parser, a pack or a rule called on its own sets the task type it was given only when
    no enclosing call set one. With no task set, no correction or suggestion role is read: every such span is checked as
    a quotation (the conservative reading).

    ``advisory`` marks a task type that a record states about itself: the ``task_type`` field of a delivered report or of
    one of its claims, which the agent's own report carries. It never widens the roles: the enclosing call's task (the
    channel's plan, or what the caller states) is kept, and with none the roles are read in no task (repair round 5,
    INV-QROLE-1: outside the channel a report that declared a marking task for an analysis answer took an altered
    quotation after a correction frame out of the checks)."""
    if not authoritative and _QUOTATION_TASK.get() is not None:
        yield
        return
    token = _QUOTATION_TASK.set(task_type if isinstance(task_type, str) and not advisory else "")
    try:
        yield
    finally:
        _QUOTATION_TASK.reset(token)


def feedback_task(feedback: Optional[bool] = None) -> bool:
    """Whether the roles are read in a feedback task: ``feedback`` when given, else the task the enclosing
    :func:`quotation_task` set (none: False)."""
    if feedback is not None:
        return bool(feedback)
    return corrections_apply(_QUOTATION_TASK.get())


#: The task type each report a parser of this process built was read in (:func:`in_quotation_task`), so the packs that run on
#: the same report read its quotations under the same task (:func:`parse_task_of`). Keyed by the report's content (its id, its own
#: task type field, its original response and its claims), so a copy of the report (the overseer's journaled one) finds the same
#: task, and a report this process did not parse (one delivered as a mapping, whatever task type it names) finds none. Bounded:
#: the most recent reports.
_PARSE_TASKS: "OrderedDict[str, str]" = OrderedDict()
_PARSE_TASKS_MAX = 4096
_PARSE_TASKS_LOCK = threading.Lock()


def _parse_key(report: object) -> Optional[str]:
    try:
        content = [getattr(report, "report_id"), getattr(report, "task_type"), getattr(report, "original_response"),
                   [[c.claim_id, c.claim_text] for c in getattr(report, "claims")]]
        return hashlib.sha256(json.dumps(content, ensure_ascii=False).encode("utf-8", "surrogatepass")).hexdigest()
    except (AttributeError, TypeError, ValueError):
        return None  # not a report: no task is known for it


def _remember_parse_task(report: object, task_type: Optional[str]) -> None:
    key = _parse_key(report) if task_type is not None else None
    if key is None:
        return
    with _PARSE_TASKS_LOCK:
        _PARSE_TASKS[key] = task_type
        _PARSE_TASKS.move_to_end(key)
        while len(_PARSE_TASKS) > _PARSE_TASKS_MAX:
            _PARSE_TASKS.popitem(last=False)


def parse_task_of(report: object) -> Optional[str]:
    """The task type under which a parser of this process read the quotations of ``report`` (the task its
    :func:`in_quotation_task` set, or an enclosing call's), or None for a report no parser here built: a branch reads the
    report's quotations again in its packs under that same task, so a correction the parser left out of the quotations is
    not read as an unaccounted quotation of the claim (integration gate 1). A report delivered as a mapping finds no task,
    whatever its own ``task_type`` field says (that field is advisory, repair round 5, INV-QROLE-1)."""
    key = _parse_key(report)
    if key is None:
        return None
    with _PARSE_TASKS_LOCK:
        return _PARSE_TASKS.get(key)


def in_quotation_task(fn):
    """Decorator for a parser's ``parse_response``: its quotations are read in the task type it is given (its keyword
    ``task_type``, else the signature's default), unless an enclosing call (the channel) already set the task. The task the
    parse was read in is remembered for the report it returns (:func:`parse_task_of`)."""
    import inspect
    param = inspect.signature(fn).parameters.get("task_type")
    default = param.default if param is not None and param.default is not inspect.Parameter.empty else None

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with quotation_task(kwargs.get("task_type", default)):
            report = fn(*args, **kwargs)
            _remember_parse_task(report, _QUOTATION_TASK.get())
            return report
    return wrapper


#: Function words a writer quotes to MENTION them (a grammatical term, 'without "like" or "as"'), never to cite a source.
MENTION_FUNCTION_WORDS: frozenset[str] = frozenset({"like", "as", "and", "but", "or", "the", "a", "an", "of", "to", "in", "so", "if", "because"})


#: Connectives a writer may name as words: a quoted one is a mention only right after a naming frame
#: (:data:`_NAMING_FRAME_RE`: 'the word "although"', 'the connective "however"'; repair round 1, re-run review ADV-07).
#: Without the frame it may cite the text ('the unfinished "although" that ends the stanza', 'linked by "Also" and
#: "When"'), so it stays a quotation and is checked.
MENTION_CONNECTIVES: frozenset[str] = frozenset({
    "although", "though", "however", "therefore", "whereas", "while", "whilst", "despite", "unless", "since", "yet", "moreover",
    "furthermore", "nevertheless", "nonetheless", "meanwhile", "thus", "hence", "besides", "instead", "otherwise", "then", "also",
    "too", "when", "because", "but", "and", "so", "or"})


#: The frame that names the span after it as a word: "the word", "the connective", "the conjunction", "the linking word",
#: "the discourse marker", "the adverb" (with "the", "a", "this" or "that"), right before the span.
_NAMING_FRAME_RE = re.compile(r"\b(?:the|a|this|that)\s+(?:word|connective|conjunction|linking\s+word|discourse\s+marker|adverb)$", re.IGNORECASE)


#: Markup and spacing between a frame and the span it governs ("→ "*x*"", "**Model:** "...").
_FRAME_GAP = " \t*_`"


#: A correction frame right before a span that needs nothing else: an arrow, or an explicit correction label.
_CORRECTION_BEFORE_RE = re.compile(r"(?:→|⟶|⇒|->|=>|\bcorrect(?:ed)?\s+(?:form|version|sentence)\s*:|\bcorrection\s*:)$", re.IGNORECASE)


#: Feedback frames that present the span after them as the corrected or model form, with no original span before it
#: (repair round 4, ADV4-04; read only in a feedback task): "it should read", "this should be", "the corrected sentence is",
#: "a better version would be", "rewrite it as", "the sentence becomes".
_FEEDBACK_BEFORE_RE = re.compile(
    r"(?:\b(?:should|would|could|must|ought\s+to|needs?\s+to|has\s+to)\s+(?:then\s+)?(?:be|read|say|become)"
    r"|\b(?:correct(?:ed|ion)?|right|accurate|better|improved|stronger|clearer|more\s+(?:accurate|natural|idiomatic|formal|precise)|model)"
    r"\s+(?:form|version|sentence|phrase|phrasing|spelling|word|wording|verb|ending|answer|option|choice|alternative|line|clause|paragraph)s?"
    r"\s*(?:(?:is|are|would\s+be|could\s+be|might\s+be|will\s+be|reads?|would\s+read)\b)?"
    r"|\b(?:rewrite|rewriting|rephrase|rephrasing|reword|rewording|redraft|redrafting|write|writing|correct|correcting)\s+"
    r"(?:it|this|that|them|these|the\s+(?:whole\s+)?(?:sentence|phrase|clause|line|paragraph|verb|ending))\s+as"
    r"|\b(?:becomes?|became|turns?\s+into|is\s+(?:corrected|changed)\s+to))\s*:?$", re.IGNORECASE)


#: What a correction leads to, after a correction span on the same line ('change "soy fue" to "fui", giving "Yo fui al
#: mercado ayer."'): the span after it is the corrected whole (feedback tasks only).
_CORRECTION_RESULT_RE = re.compile(r"(?:giving|to\s+give|which\s+gives|so\s+(?:that\s+)?(?:it|the\s+(?:sentence|line|phrase))\s+reads?|to\s+read)\s*:?$",
                                   re.IGNORECASE)


#: A correction written in words between an original span and the span that corrects it ('"x" should be "y"', '"x" should
#: read "y"', 'change "x" to "y"', 'replace "x" with "y"'): the frame names a correction only when an original span stands
#: right before it, so 'the speaker should be "free"' with no original stays a quotation and is checked. "Becomes" is a
#: correction frame only in a feedback task ('"simpático" becomes "simpática"'); in an analysis 'the "rose" becomes a
#: "canker"' describes the text, and both quotations are checked.
#: The gap patterns between two spans consume each run of spaces and markup once (possessive quantifiers: close round 2,
#: SEC-QROLE-QUADRATIC): the greedy runs they replace read a long run of spaces between two quotations again from every
#: position of it. They match exactly the strings the greedy forms matched, since a run of spaces or markup is never what
#: the next part of a pattern needs.
_WORD_CORRECTION_GAP_RE = re.compile(r"^[\s*_`]*+(?:,\s*+)?(?:should\s+(?:be|read)|is\s+(?:corrected|changed)\s+to|(?:with|by)|to|into)\s*+:?[\s*_`]*+$",
                                     re.IGNORECASE)


_BECOMES_GAP_RE = re.compile(r"^[\s*_`]*+(?:,\s*+)?(?:becomes?|became|turns?\s+into|changes?\s+to|must\s+be|needs?\s+to\s+be)\s*+:?[\s*_`]*+$", re.IGNORECASE)


#: What opens a 'change "x" to "y"' correction before its original span.
_CHANGE_BEFORE_RE = re.compile(r"\b(?:change|changing|correct|correcting|replace|replacing|swap|swapping|rewrite|rewriting)\s*$", re.IGNORECASE)


#: Where a sentence of a line starts: a label may open the line or a sentence after a stop.
_SENTENCE_START_RE = re.compile(r"[.!?;]\s+")


#: The head of a label (:data:`_CORRECTION_LABEL_RE`, :data:`_SUGGESTION_LABEL_RE` without their anchors and their closing
#: run of spaces and markup), read once from where a line or a sentence starts (:class:`_LineIndex`). The colon a head ends
#: at is the first one after the label word, so a stretch matches the anchored label pattern exactly when it holds the head
#: and nothing but spaces and markup after its colon.
_CORRECTION_LABEL_HEAD_RE = re.compile(r"[\s>*_#\d.)(-]*+(?:model(?:\s+(?:answer|sentence|version|paragraph))?|corrected(?:\s+(?:version|sentence|form))?|correction"
                                       r"|better|improved(?:\s+version)?|rewrite|rewritten)\b[^:\"“”«»\n]{0,40}:", re.IGNORECASE)


_MARKUP_RUN_RE = re.compile(r"[\s*_`]*+")


#: A suggestion frame right before a span: "you could write / add / use / say / try", "instead write", "write instead".
_SUGGESTION_BEFORE_RE = re.compile(r"(?:\byou\s+(?:could|might|can|may)\s+(?:also\s+)?(?:write|add|use|say|try)|\binstead\s+write|\bwrite\s+instead)\s*:?$",
                                   re.IGNORECASE)


#: "try" or "add" as an imperative right before a span: at the start of the line or of a sentence or clause, or after "or",
#: "and", "perhaps", "maybe", "please" or "then" ("Try "para ayudar"", "or add "sin embargo""); never a reporting use ("the
#: speaker goes on to add "...""), which stays a quotation.
_IMPERATIVE_SUGGESTION_RE = re.compile(r"(?:^|[.!?:;(—–]\s*|\b(?:or|and|perhaps|maybe|please|then)\s+)(?:try|add|write|use|say|put|choose)\s*:?$", re.IGNORECASE)


_SUGGESTION_LABEL_HEAD_RE = re.compile(r"[\s>*_#\d.)(-]*+suggestions?\b[^:\"“”«»\n]{0,40}:", re.IGNORECASE)


#: A negating frame that mentions a span of any length: the writer says the text does not use it ('never uses "I"'), avoids
#: or leaves it out ('the writer avoids "very"'), or could have used it but did not ('the writer could have used "moved"';
#: repair round 4, ADV4-03). Each says the words are NOT the text's, so the span attributes nothing to the text.
_MENTION_ANY_BEFORE_RE = re.compile(
    r"(?:\bnever\s+uses?|\bdoes\s+not\s+use|\bdoesn['’]t\s+use|\bdo\s+not\s+use|\bdon['’]t\s+use|\bdid\s+not\s+use|\bdidn['’]t\s+use"
    r"|\bavoids?|\bavoided|\bavoiding|\bomits?|\bomitted|\bomitting|\bleaves\s+out|\bleft\s+out|\bleaving\s+out"
    r"|\b(?:could|might|would|may)\s+(?:also\s+)?(?:have|instead\s+have)\s+(?:used|written|said|chosen|picked|put|preferred)"
    r"|\b(?:chose|chooses|choosing|decided|decides)\s+not\s+to\s+(?:use|write|say)"
    r"|\b(?:instead\s+of|rather\s+than|in\s+place\s+of)\s+(?:using|writing|saying|choosing))$", re.IGNORECASE)


#: A negated report that mentions what the text does NOT say ('It does not say that the plan has "failed"', 'the source never
#: calls it "a success"'): the span is the writer's word for a claim the text does not make, never a quotation of it
#: (repair round 1, re-run review A-FA-MENTION). The report verb may stand up to 80 characters before the span, in the
#: same clause: no other quotation mark, no comma, semicolon or colon and no clause word ("so", "but", "which", "whose",
#: "because", ...) between them ('The poem never mentions the war, so ... whose "dates and figures"' quotes).
_MENTION_NEGATED_REPORT_RE = re.compile(
    r"(?:\bdoes\s+not|\bdoesn['’]t|\bdid\s+not|\bdidn['’]t|\bdo\s+not|\bdon['’]t|\bnever|\bnowhere)\s+(?:say|says|said|state|states|stated|claim|claims|"
    r"claimed|call|calls|called|describe|describes|described|mention|mentions|mentioned|write|writes|wrote|suggest|suggests|suggested)\b"
    r"(?![^\n]*?\b(?:so|but|which|whose|because|while|whereas|although|though)\b[^\n]*$)[^.!?\n\"“”«»,;:]{0,80}$", re.IGNORECASE)


#: A contrast that corrects: 'Not "We was" but "We were"': the span after "but" corrects the span after "not" (feedback
#: tasks only).
_NOT_BEFORE_RE = re.compile(r"(?:^|[.!?:;(—–]\s*|\s)not\s*$", re.IGNORECASE)


_BUT_GAP_RE = re.compile(r"^[\s*_`]*+,?\s*+but[\s*_`]*+$", re.IGNORECASE)  # possessive runs: each read once (close round 2)


#: A negating frame that mentions a short span (at most :data:`_SHORT_MENTION_WORDS` words): 'without "like" or "as"', 'with no
#: "rhyme"'. A longer span after "without" ('departs without "a backward glance"') may be the text's own words, so it stays a
#: quotation and is checked. A contrast ("unlike", "rather than", "instead of") is no such frame: what it sets aside is as
#: often the text's own words ('Unlike "the bright fields" of the morning, the river ...') as a word the text does not use, so the
#: span after it stays a quotation and is checked, as on the committed base (close round 2, DIFF-02: the contrast frames,
#: "unlike" among them since repair round 5, ADV5-08, hid an invented quotation presented as the text's; the mention frames
#: had been narrowed by close round 1, so this reading is reverted for its whole class under the round's convergence rule).
_MENTION_SHORT_BEFORE_RE = re.compile(r"(?:\bwithout|\bwith\s+no|\bno)$", re.IGNORECASE)


_SHORT_MENTION_WORDS = 3


#: A verb phrase the writer negates with a single quoted word as its verb or object ('the waves do not "crash"', 'the speaker
#: is not "afraid"'): the text is said NOT to have that word (repair round 5, ADV5-08). Only one word: a longer span after a
#: negated verb ('The king does not "rule with mercy"', 'the speaker is not "utterly defeated"') may present words as the
#: source's, so it stays a quotation and is checked (close round 1, rerun-verify6-weakened-negated-quotation-mention). A bare
#: "not" after a comma or opening a line ('Not "x" but "y"', '"x", not "y"') is a contrast and stays a quotation.
_MENTION_NEGATED_VERB_BEFORE_RE = re.compile(r"(?:\b(?:do|does|did|is|are|was|were|has|have|had|will|would|can|could|should|must)\s+not"
                                             r"|\b(?:don|doesn|didn|isn|aren|wasn|weren|hasn|haven|hadn|won|wouldn|can|couldn|shouldn|mustn)['’]t)$",
                                             re.IGNORECASE)


#: A credit to a source right after a span ('..., as the chronicle claims', '(as the poet puts it)', '— as the report says'):
#: the span is given as the source's words, so it stays a quotation whatever frame stands before it (close round 1).
_CREDIT_AFTER_RE = re.compile(r"^[\s*_`]*[,;(—–-]?[ \t]*as[ \t]+(?:(?:the|a|an|this|that|his|her|its|their)[ \t]+)?(?:[^\W\d_]+[ \t]+){0,3}?"
                              r"(?:says?|said|claims?|claimed|states?|stated|writes?|wrote|puts[ \t]+it|put[ \t]+it|calls?[ \t]+it|has[ \t]+it|reports?|"
                              r"reported|records?|recorded|notes?|noted|tells[ \t]+us|describes?[ \t]+it|insists?)\b", re.IGNORECASE)


#: An example the writer offers of a kind of word, with an indefinite article ('a neutral word such as "moved"', 'a calm word
#: like "rolled"', 'an alternative such as "drifted"'): a word the text could have used, not one it uses (repair round 5,
#: ADV5-08). A plural or definite phrase ('violent verbs such as "smashed"', 'the verb "smashed"') names the text's own words
#: and stays a quotation.
_MENTION_EXAMPLE_BEFORE_RE = re.compile(
    r"\b(?:a|an|any|another|some\s+other)\s+(?:[^\W\d_]+[\s,]+){0,3}?(?:word|verb|noun|adjective|adverb|term|phrase|expression|synonym|"
    r"alternative|option|choice|wording)\s*,?\s*(?:such\s+as|like|e\.?\s?g\.?,?|for\s+example,?|for\s+instance,?)$", re.IGNORECASE)


#: A reporting verb under a negation right before a span ('the poet does not write "splashed"', 'never says "afraid"') is an
#: attribution like any other, so the span is a quotation and is checked, as on the committed base. Repair round 5 (ADV5-08)
#: read such a span as a mention, with one word allowed between the negation and the verb; that also read 'not only writes
#: "..."', 'does not just say "..."' and 'not only says "..."', which affirm the attribution, as "the text does not say
#: this", so an invented quotation put after them was never checked (close round 3, INV-QR-1). The mention frames of
#: ADV5-08 had been narrowed by close round 1, so under the round's convergence rule this reading is reverted for its whole
#: class (every negated reporting verb right before a span); a negated report with words between the verb and the span ('It
#: does not say that the plan has "failed"', 'never calls it "a success"': :data:`_MENTION_NEGATED_REPORT_RE`) keeps its
#: mention, as before repair round 5.
#: What joins a span to the one before it in a list that the first span's frame governs ('"x" → "y", or "z"', '"like" or "as"').
_LIST_JOIN_RE = re.compile(r"^[\s*_`]*+(?:,|;|,?\s*+(?:or|and|nor))[\s*_`]*+$", re.IGNORECASE)  # possessive runs (close round 2)


#: An attribution before a span or a citation after it: such a span stays a quotation whatever frame surrounds it, so a
#: writer cannot pass words off as a source's by also calling them a correction.
_ATTRIBUTION_BEFORE_RE = re.compile(r"\b(?:says?|said|states?|stated|writes?|wrote|reads?|calls?|called|describes?|described|quotes?|quoted|the\s+(?:poem|poet|text|"
                                    r"extract|passage|source|author|speaker|narrator|line|document))\s*[,:]?$", re.IGNORECASE)


_CITATION_AFTER_RE = re.compile(r"^[\s*_`]*[(\[]\s*(?:l{1,2}\.?|lines?|stanza|para(?:graph)?|p{1,2}\.?|page|source)\s*\d", re.IGNORECASE)


#: A frame whose subject is a quotation of a text ('the last quotation should read "..."', 'your quote "x" should be "y"',
#: 'the poem's exact words are "..."'): the span after it is the text's words as they should be quoted, so it stays a
#: quotation and is checked even in a feedback task (repair round 4).
_QUOTATION_SUBJECT_RE = re.compile(r"(?:\b(?:the|your|his|her|their|this|that|each|every|last|first|second|third|final|opening|closing)\s+(?:[^\W\d_]+\s+){0,2}"
                                   r"(?:quotations?|quotes?|citations?|excerpts?)"
                                   r"|\b(?:poem|poet|text|extract|passage|source|author|writer|novel|play|speaker)['’]s\s+(?:own\s+|exact\s+|actual\s+)?"
                                   r"(?:words?|line|phrase|wording))\b(?:(?![.!?;]\s).){0,80}$", re.IGNORECASE)


#: A reporting verb under a modal prescribes, it does not report ("it should read", "the sentence would say"): in a feedback
#: task such a frame is a correction, not an attribution.
_PRESCRIBED_REPORT_RE = re.compile(r"\b(?:should|would|could|must|ought\s+to|needs?\s+to|has\s+to)\s+(?:then\s+)?(?:read|say|state)\s*[,:]?$", re.IGNORECASE)


_ARROW_AFTER_RE = re.compile(r"^[\s*_`]*(?:→|⟶|⇒|->|=>)")


_QUOTE_STRIP = "\"'“”‘’«»„‟ *_`.,;:!?"


class _LineIndex:
    """Where the lines of one text start, and the sentences of each line (:data:`_SENTENCE_START_RE`), read once: the
    quotation-role reader looks them up for each span by bisection, so the roles of many spans on one long line cost one
    pass over the text (close round 2, SEC-QROLE-QUADRATIC: the reader read the whole line before every span, and every
    earlier span for each span). A label head (:data:`_CORRECTION_LABEL_HEAD_RE`) is read once from each place a line or a
    sentence starts. Nothing here changes a role: each lookup answers what the slice it replaces answered."""

    __slots__ = ("text", "newlines", "_sentences", "_heads")

    def __init__(self, text: str) -> None:
        self.text = text
        self.newlines = [m.start() for m in re.finditer("\n", text)]
        self._sentences: dict[int, tuple[list[int], list[int]]] = {}
        self._heads: dict[tuple[int, int], Optional[tuple[int, int]]] = {}

    def line_start(self, pos: int) -> int:
        """``text.rfind("\\n", 0, pos) + 1``."""
        k = bisect.bisect_left(self.newlines, pos)
        return self.newlines[k - 1] + 1 if k else 0

    def line_end(self, pos: int) -> int:
        """The first line break at or after ``pos``, else the end of the text."""
        k = bisect.bisect_left(self.newlines, pos)
        return self.newlines[k] if k < len(self.newlines) else len(self.text)

    def frame_before(self, start: int) -> str:
        """:func:`_frame_before` with the line start looked up."""
        return self.text[max(self.line_start(start), start - 120):start].rstrip(_FRAME_GAP)

    def _sentence_marks(self, ls: int) -> tuple[list[int], list[int]]:
        got = self._sentences.get(ls)
        if got is None:
            starts: list[int] = []
            ends: list[int] = []
            for m in _SENTENCE_START_RE.finditer(self.text, ls, self.line_end(ls)):
                starts.append(m.start())
                ends.append(m.end())
            got = self._sentences[ls] = (starts, ends)
        return got

    def _head(self, s: int, head: "re.Pattern[str]") -> Optional[tuple[int, int]]:
        """``(the end of the label head read from s, the end of the run of spaces and markup after it)``, or None."""
        key = (s, id(head))
        if key not in self._heads:
            le = self.line_end(s)
            m = head.match(self.text, s, le)
            self._heads[key] = None if m is None else (m.end(), _MARKUP_RUN_RE.match(self.text, m.end(), le).end())
        return self._heads[key]

    def label_governs(self, a: int, head: "re.Pattern[str]") -> bool:
        """Whether a label opens the line of the span at ``a``, or the last sentence of that line before it, and nothing but
        spaces and markup stands between its colon and the span: what matching the anchored label pattern on the line's
        text before the span from the line start, or from the end of its last sentence mark, read (sentence marks never
        straddle a span's opening mark, so each is read from the whole line once)."""
        ls = self.line_start(a)
        starts, ends = self._sentence_marks(ls)
        k = bisect.bisect_left(starts, a)
        for s in (ls, ends[k - 1] if k else None):
            if s is None:
                continue
            got = self._head(s, head)
            if got is not None and got[0] <= a <= got[1]:
                return True
        return False


def _frame_before(text: str, start: int, lines: "Optional[_LineIndex]" = None) -> str:
    """The text before a span on its line, with the markup and spaces next to the span removed."""
    if lines is not None:
        return lines.frame_before(start)
    line_start = text.rfind("\n", 0, start) + 1
    return text[max(line_start, start - 120):start].rstrip(_FRAME_GAP)


def _word_correction(text: str, spans: Sequence[tuple[int, int, str]], k: int, *, feedback: bool, lines: "Optional[_LineIndex]" = None) -> bool:
    """Whether span ``k`` is the corrected form of the span right before it on its line, joined by a correction written in
    words ('"x" should be "y"', 'change "x" to "y"', 'replace "x" with "y"'; in a feedback task also '"x" becomes "y"')."""
    if k == 0:
        return False
    pa, pb, _inner = spans[k - 1]
    a = spans[k][0]
    if pb > a or "\n" in text[pb:a]:
        return False
    gap = text[pb:a]
    if feedback and _BECOMES_GAP_RE.match(gap) is not None:
        return True
    if _WORD_CORRECTION_GAP_RE.match(gap) is None:
        return False
    word = gap.strip(" \t*_`:,").lower()
    if word in ("to", "into", "with", "by"):  # 'change "x" to "y"', 'replace "x" with "y"': the verb stands before the original
        return _CHANGE_BEFORE_RE.search(_frame_before(text, pa, lines)) is not None
    return True


#: Role lists of at most this many texts are kept (the parser, the packs and the structural checks read one answer's roles
#: six to nine times); a text is kept with the roles read from it, so a cached answer is the one the reader gives.
_ROLE_CACHE_SIZE = 16


def _span_roles(text: str, spans: Sequence[tuple[int, int, str]], *, feedback: Optional[bool] = None) -> list[str]:
    """The role of every span of ``spans`` (in order), by closed frames only (see :data:`QUOTATION_ROLES`):

    * ``correction`` (a feedback task only, :func:`feedback_task`): the span follows an arrow or an explicit correction
      label ("correct form:", "correction:"), or a feedback frame with no original before it ("it should read", "the
      corrected sentence is", "a better version would be", "rewrite it as"), or it corrects the span right before it on its
      line with a correction in words ('"x" should be "y"', '"x" becomes "y"', 'change "x" to "y"', 'replace "x" with
      "y"', 'not "x" but "y"'), or follows what a correction gives (', giving "..."'), or it opens a line or a sentence
      under a correction label ("Model:", "Corrected:", "Better:") without being the original an arrow corrects, or it
      continues a list the previous correction span opened ('→ "x", or "y"');
    * ``suggestion`` (a feedback task only): it follows "you could write / add / use / say / try", "instead write", or an
      imperative "try", "add", "write", "use", "say", "put" or "choose" (at the start of a line, sentence or clause:
      'write "my friend and I"', 'use "we went"'), or sits on a "Suggestion" line without being the original an arrow
      corrects;
    * ``mention`` (any task): it is one quoted function word (:data:`MENTION_FUNCTION_WORDS`), or one connective a naming
      frame names as a word (:data:`MENTION_CONNECTIVES`: 'the word "although"', 'the connective "however"'), or follows
      a frame that says the text does not use the words ("never uses", "does not use", "avoids", "leaves out", "could have
      used"), or a negated report ('It does not say that the plan has "failed"'), or is a span of at most three words
      after "without", "with no" or "no" (never after a contrast: "unlike", "rather than", "instead of"), or continues a list
      such a frame opened;
    * ``quotation``: anything else, and any span that an attribution precedes (a negated reporting verb right before the
      span included: 'never says "x"', 'not only writes "x"', 'does not just say "x"'; close round 3, INV-QR-1) or a line
      citation follows (an imperative "write" or "say" at the start of a clause has no subject and attributes nothing: it
      is a suggestion in a feedback task and a quotation in any other).

    A content word under "the word" or "the verb" stays a quotation ("the verb 'smashed'" is still checked), and so does a
    span after a word frame with no original before it ('the speaker should be "free"' outside a feedback task). Outside a
    feedback task no frame makes a span the writer's own words except a mention, which says the words are not the
    text's: an arrow, a "Model:" label, an imperative, 'Not "x" but "y"' or '"x" should be "y"' in a literary or a
    source analysis leaves the span a quotation, so an altered quotation framed that way is still named (repair round 4,
    INV-Q1).

    Linear in the text (close round 2, SEC-QROLE-QUADRATIC): the line of each span, its sentence marks and its label heads
    are looked up in a :class:`_LineIndex` read once, an earlier correction on the span's line is known from the end of the
    last correction span, and the gap patterns read each run of spaces once."""
    return list(_roles_read(text, tuple(spans), feedback_task(feedback)))


def _roles_read(text: str, spans: tuple[tuple[int, int, str], ...], feedback_read: bool) -> tuple[str, ...]:
    if len(spans) < 2:
        return _roles_of(text, spans, feedback_read)
    return _roles_cached(text, spans, feedback_read)


@functools.lru_cache(maxsize=_ROLE_CACHE_SIZE)
def _roles_cached(text: str, spans: tuple[tuple[int, int, str], ...], feedback_read: bool) -> tuple[str, ...]:
    return _roles_of(text, spans, feedback_read)


def _roles_of(text: str, spans: tuple[tuple[int, int, str], ...], feedback_read: bool) -> tuple[str, ...]:
    lines = _LineIndex(text)
    roles: list[str] = []
    last_correction_end = -1  # the end of the last span read as a correction
    for k, (a, b, inner) in enumerate(spans):
        before = lines.frame_before(a)
        # a correction or suggestion frame whose subject is a quotation prescribes the text's words: no role of the writer's own
        fb = feedback_read and _QUOTATION_SUBJECT_RE.search(before) is None
        after = text[b:b + 24]
        core = inner.strip(_QUOTE_STRIP).lower()
        role = "quotation"
        imperative = _IMPERATIVE_SUGGESTION_RE.search(before) is not None  # 'write "x"', 'say "y"': no subject, so no attribution
        prescribed = fb and _PRESCRIBED_REPORT_RE.search(before) is not None  # 'it should read "..."': no report of a text
        # a negated reporting verb right before the span ('never says "x"', 'not only writes "x"') is an attribution like any
        # other: the span is a quotation and is checked (close round 3, INV-QR-1: the repair round 5 reading is reverted)
        if ((_ATTRIBUTION_BEFORE_RE.search(before) and not (imperative and fb) and not prescribed) or _CITATION_AFTER_RE.match(after)
                or _CREDIT_AFTER_RE.match(text[b:b + 120])):
            roles.append(role)
            continue
        gap = text[spans[k - 1][1]:a] if k > 0 and spans[k - 1][1] <= a else None
        joined = gap is not None and _LIST_JOIN_RE.match(gap) is not None
        arrow_follows = _ARROW_AFTER_RE.match(after) is not None
        contrast = (gap is not None and _BUT_GAP_RE.match(gap) is not None
                    and _NOT_BEFORE_RE.search(lines.frame_before(spans[k - 1][0])) is not None)
        # an earlier correction span that ends on this span's line (no line break between its end and this span)
        corrected_before = last_correction_end >= lines.line_start(a)
        if fb and (_CORRECTION_BEFORE_RE.search(before) or _word_correction(text, spans, k, feedback=fb, lines=lines) or contrast
                   or (_FEEDBACK_BEFORE_RE.search(before) and not arrow_follows)
                   or (corrected_before and _CORRECTION_RESULT_RE.search(before))
                   or (lines.label_governs(a, _CORRECTION_LABEL_HEAD_RE) and not arrow_follows)):
            role = "correction"
        elif joined and roles[k - 1] in ("correction", "mention", "suggestion"):
            role = roles[k - 1]
        elif fb and (_SUGGESTION_BEFORE_RE.search(before) or imperative
                     or (lines.label_governs(a, _SUGGESTION_LABEL_HEAD_RE) and not arrow_follows)):
            role = "suggestion"
        elif (core in MENTION_FUNCTION_WORDS or (core in MENTION_CONNECTIVES and _NAMING_FRAME_RE.search(before))
              or _MENTION_ANY_BEFORE_RE.search(before) or _MENTION_NEGATED_REPORT_RE.search(before)
              or ((_MENTION_SHORT_BEFORE_RE.search(before) or _MENTION_EXAMPLE_BEFORE_RE.search(before)) and len(core.split()) <= _SHORT_MENTION_WORDS)
              or (_MENTION_NEGATED_VERB_BEFORE_RE.search(before) and len(core.split()) == 1)):
            role = "mention"
        if role == "correction":
            last_correction_end = max(last_correction_end, b)
        roles.append(role)
    return tuple(roles)


#: The frame right before a quoted span that says the text lacks the span's words ('has no "like"', 'without "like"', 'never
#: uses "I"', 'lacks the word "x"', 'neither "like" ...'): the core pack (CORE-SRC-003), the channel (INT-REQ-003) and the
#: Overseer (FID-004) read such a span as a mention of a word, not a quotation of a text, and verify nothing of it. Moved here
#: unchanged from ``branches.packs`` (which keeps its names for it), so a parser reads the same frames (integration gate 1).
ABSENT_BEFORE_RE = re.compile(
    r"(?:\b(?:has|have|had|contains?|uses?|includes?|gives?|offers?)\s+no\s+(?:(?:word|words|term|mention|instance|use)\s+(?:of\s+|like\s+)?)?"
    r"|\b(?:never|nowhere)\s+(?:says?|uses?|writes?|mentions?|contains?|includes?|states?)\s+(?:the\s+word\s+)?"
    r"|\b(?:does|did|do)\s*(?:not|n['’]t)\s+(?:say|use|write|mention|contain|include|state)\s+(?:the\s+word\s+)?"
    r"|\blacks?\s+(?:the\s+word\s+)?|\bwithout\s+(?:the\s+word\s+|a\s+|an\s+)?|\bno\s+(?:word\s+)?|\bneither\s+)$", re.IGNORECASE)
#: What may stand between two quoted words of one absent mention: 'has no "like" or "as"', 'neither "like" nor "as"'.
ABSENT_JOIN_RE = re.compile(r"^\s*(?:,\s*)?(?:or|nor|and)\s+$|^\s*,\s*$", re.IGNORECASE)


#: A quoted statement the sentence judges true or false ('so "more than twenty" is false', '"the war ended in 1917" is incorrect'): the
#: writer's words for the statement under judgement (an English gloss of a request's Spanish statement), a mention, not a quotation of a
#: text (c1 sp-t14). Read on the characters right after the closing mark (``match(text, end, end + 48)``: anchored there).
JUDGED_AFTER_RE = re.compile(r"[\s*_`'’\"”»]{0,4}(?:is|are|was|were)\s++(?:not\s++|therefore\s++|thus\s++)?(?:false|true|correct|incorrect|wrong|right"
                             r"|untrue|inaccurate|accurate|falso|falsa|verdadero|verdadera)\b", re.IGNORECASE)
#: The word the reader is told to reply with ('Reply "approve" and I will write ...', 'just answer "yes"'): an instruction, a mention of a
#: word, not a quotation (c1 ps-p8d). Read on the characters right before the opening mark.
REPLY_BEFORE_RE = re.compile(r"(?:^|[.!?:;(—–]\s*+|\b(?:just|simply|please|or|and|then)\s++)(?:reply|respond|answer|type)(?:\s++with)?\s*+[:,]?[\s*_`]*+$",
                             re.IGNORECASE)


#: A quoted phrase introduced as a label or a definition ('Let E be "at least one blue" and F be "both blue".', 'we call it "the gap"',
#: 'a process called "osmosis"', 'define S as "a success"', 'denoted by "n"', 'stands for "not applicable"'): the writer's own name for
#: something, a mention, never a quotation of a text (round-9 clearance c2b, maa-t15 m11.1 drew CORE-SRC-003). Naming is the writer's
#: own ("we call it", "let us call") or a name with no speaker ("called" right before the mark); words another speaker gave ('One
#: minister called it "a parliament that could only say no"', 'Marx calls them "..."') stay a quotation. Read on the characters right
#: before the opening mark, every run bounded.
LABEL_BEFORE_RE = re.compile(r"(?:\blet[ \t]{1,3}[^\W\d_]{1,12}[ \t]{1,3}be|\band[ \t]{1,3}[^\W\d_]{1,12}[ \t]{1,3}be"
                             r"|\b(?:we|i|let[ \t]{1,3}us|let['’]s)[ \t]{1,3}call(?:ed)?(?:[ \t]{1,3}(?:it|this|them|these|that))?|\bcalled"
                             r"|\bdefine[ds]?[ \t]{1,3}[^\W\d_]{1,12}[ \t]{1,3}as|\bdenoted?[ \t]{1,3}by|\bstands?[ \t]{1,3}for)[ \t]{0,3}[*_`]{0,2}$", re.IGNORECASE)


def _absent_flags(text: str, spans: Sequence[tuple[int, int, str]]) -> list[bool]:
    """For each span, whether :data:`ABSENT_BEFORE_RE` ends right before it (read in the 60 characters before it), or it
    follows such a span with only :data:`ABSENT_JOIN_RE` between them; or it is a statement the sentence judges true or false
    (:data:`JUDGED_AFTER_RE`), the word the reader is told to reply with (:data:`REPLY_BEFORE_RE`) or a label or a definition the
    writer introduces (:data:`LABEL_BEFORE_RE`)."""
    out: list[bool] = []
    prev_absent_end: Optional[int] = None
    for s, e, _inner in spans:
        before = text[max(0, s - 60): s]
        if (ABSENT_BEFORE_RE.search(before) or (prev_absent_end is not None and ABSENT_JOIN_RE.match(text[prev_absent_end: s]))
                or JUDGED_AFTER_RE.match(text, e, e + 48) or REPLY_BEFORE_RE.search(before) or LABEL_BEFORE_RE.search(before)):
            out.append(True)
            prev_absent_end = e
        else:
            out.append(False)
            prev_absent_end = None
    return out


def judged_or_reply_mention(text: str, start: int, end: int) -> bool:
    """Whether the quoted span ``text[start:end]`` (marks included) is a statement the sentence judges true or false
    (:data:`JUDGED_AFTER_RE`) or the word the reader is told to reply with (:data:`REPLY_BEFORE_RE`): a mention, not a quotation."""
    return JUDGED_AFTER_RE.match(text, end, end + 48) is not None or REPLY_BEFORE_RE.search(text[max(0, start - 60):start]) is not None


def absent_mentions(text: str, spans: Sequence[tuple[int, int, str]]) -> list[str]:
    """The quoted words of ``text`` that its sentence says the text lacks ('the bruise comparison has no "like" or "as"', 'the text never
    says "ayudar"'), that it judges true or false as a statement ('so "more than twenty" is false') or that it tells the reader to reply
    with ('Reply "approve" and I will write ...'): a mention of words, not a quotation of a text. The core pack (CORE-SRC-003), the
    channel (INT-REQ-003) and the Overseer read these as mentions and verify nothing of them."""
    return [inner.strip() for (_s, _e, inner), absent in zip(spans, _absent_flags(text, spans)) if absent]


def _absence_mentions(text: str, spans: Sequence[tuple[int, int, str]], roles: Sequence[str]) -> list[bool]:
    """For each span, whether the role reader reads it as a mention that says the text lacks its words: a role of
    ``mention`` read under an absence frame ("without", "with no", "no" before at most three words; "never uses", "avoids",
    "could have used"; a negated report; a negated verb before one word), an example frame ('a verb such as "x"'), or a
    span joined by "or", "and" or a comma to such a mention ('without "like" or "as"'). A mention by the closed list of
    function words alone, or by a naming frame ('the conjunction "But"'), is not one: it names a word of the text."""
    lines = _LineIndex(text)
    out: list[bool] = []
    for k, ((a, _b, inner), role) in enumerate(zip(spans, roles)):
        absent = False
        if role == "mention":
            before = lines.frame_before(a)
            words = len(inner.strip(_QUOTE_STRIP).split())
            absent = bool(_MENTION_ANY_BEFORE_RE.search(before) or _MENTION_NEGATED_REPORT_RE.search(before)
                          or ((_MENTION_SHORT_BEFORE_RE.search(before) or _MENTION_EXAMPLE_BEFORE_RE.search(before)) and words <= _SHORT_MENTION_WORDS)
                          or (_MENTION_NEGATED_VERB_BEFORE_RE.search(before) and words == 1))
            if not absent and k and out[k - 1] and spans[k - 1][1] <= a:
                absent = _LIST_JOIN_RE.match(text[spans[k - 1][1]:a]) is not None
        out.append(absent)
    return out


def absent_word_mentions(text: str, *, min_single_words: int = 2, feedback: Optional[bool] = None) -> list[tuple[int, int, str]]:
    """The quoted spans of ``text`` (:func:`find_quotation_spans`) that say the text lacks their words, by both readers: the
    role reader reads the span as a mention under an absence frame (:func:`_absence_mentions`: 'without "like" or "as"',
    'with no "like"', 'has no "like"'), and the frame reader by which the core pack, the channel and the Overseer leave a
    mention unverified reads it as absent (:func:`absent_mentions`). The shared attribution rule credits such a span to no
    text when no supplied text holds its words (``sources.attribute_excerpt``, every parser; end-to-end B6): it is a mention
    of a word the sentence says the text lacks, so crediting it to a named text or to the text under analysis would refute
    the writer for the very absence the sentence states. Only a span of at most three words is one (the length of a
    mention under "without" or "no"): a longer span joined to a mention by "and" or a comma ('has no "apology", and "the
    treaty was a crime of revenge" is its verdict') may be words the sentence gives as the text's, so it keeps the ordinary
    credit and is checked. A span only one reader calls a mention keeps the ordinary credit too, so it is checked as
    before: a negated reporting verb right before it ('never says "x"') is an attribution for the role reader (close round
    3, INV-QR-1), and 'avoids "x"' is no frame of the other."""
    spans = find_quotation_spans(text, min_single_words=min_single_words)
    if not spans:
        return []
    roles = _span_roles(text, spans, feedback=feedback)
    if "mention" not in roles:
        return []
    by_role = _absence_mentions(text, spans, roles)
    by_frame = _absent_flags(text, spans)
    return [sp for sp, r, f in zip(spans, by_role, by_frame)
            if r and f and len(sp[2].strip(_QUOTE_STRIP).split()) <= _SHORT_MENTION_WORDS]


def parser_quotation_spans(text: str, *, min_single_words: int = 2, feedback: Optional[bool] = None) -> list[tuple[int, int, str]]:
    """The quoted spans of ``text`` (:func:`find_quotation_spans`) a parser reads as quotations: the spans it credits to a
    supplied text, carries as quotation claims or records as credited to no text. A correction or a suggestion is the
    writer's own words and is left out (end-to-end B5; integration gate 1): read only in a marking, feedback, correction or
    editing task (:func:`_span_roles`, :func:`quotation_task`; the parsers read the task type they are given,
    :func:`in_quotation_task`), it is the corrected form after an arrow ('"una mujer muy simpático" → "una mujer muy
    simpática"'), after "should be", under a "Model:" label, and the like. The student's own words before the arrow stay
    quotations and are checked.

    Every other span is kept, every mention included: a mention stays a quotation claim, and the checks that verify words
    against a source leave it unverified by their own mention readers (a mention of words the text lacks, 'without "like"
    or "as"', is credited to no text when no text holds it: ``sources.attribute_excerpt``, :func:`absent_word_mentions`).
    Outside a feedback task the result is :func:`find_quotation_spans` itself, read without the roles: an arrow, a "Model:"
    label or a correction in words there leaves the span a quotation, so an altered quotation framed that way is still
    checked (repair round 4, INV-Q1). Masking text and testing whether a position lies inside a quotation keep
    :func:`find_quotation_spans`."""
    spans = find_quotation_spans(text, min_single_words=min_single_words)
    if not spans or not feedback_task(feedback):
        return spans  # the roles read no correction or suggestion outside a feedback task: no role is read there at all
    roles = _span_roles(text, spans, feedback=feedback)
    if "correction" not in roles and "suggestion" not in roles:
        return spans
    return [sp for sp, role in zip(spans, roles) if role not in ("correction", "suggestion")]


def cited_quotation_spans(text: str, *, min_single_words: int = 2, feedback: Optional[bool] = None) -> list[tuple[int, int, str]]:
    """The quoted spans of ``text`` (:func:`find_quotation_spans`) whose role is ``quotation`` (:func:`quotation_role`): the
    spans a check of words against a source, or an attribution to a source, reads. A correction, a suggestion or a
    mention is the writer's own words: it is never checked or presented as a quotation, and carries no source reference.
    Masking text and testing whether a position lies inside a quotation keep :func:`find_quotation_spans`, so every
    quoted span stays masked whatever its role."""
    spans = find_quotation_spans(text, min_single_words=min_single_words)
    if not spans:
        return []
    return [sp for sp, role in zip(spans, _span_roles(text, spans, feedback=feedback)) if role == "quotation"]


# --------------------------------------------------------------------------------------------- argument diagnosis readers (2)
# Readers of a sentence that concludes from an earlier one, for the argument diagnosis and its tests. Additions only: no
# parser of this tree calls them.

#: Doubled final consonants a stem keeps after "-ing" or "-ed" ("cutting" is "cutt"); folded on both sides of a comparison.
_DOUBLED_FINALS = frozenset("bdgmnprt")


def _word_stems(text: str) -> set[str]:
    """The content stems of ``text`` that are words of three or more letters (numbers and one-letter symbols such as ``y``
    say nothing about what a clause restates), a doubled final consonant folded ("cutting" meets "cut")."""
    out: set[str] = set()
    for s in lexis.content_stems(text):
        if len(s) >= 3 and s.isalpha():
            out.add(s[:-1] if len(s) >= 4 and s[-1] == s[-2] and s[-1] in _DOUBLED_FINALS else s)
    return out


def concludes_from_earlier(sentence: str, earlier: Sequence[str]) -> bool:
    """Whether ``sentence`` draws its conclusion from a sentence before it: it opens with a reason clause
    (:func:`leading_reason_clause`) that restates one of ``earlier``: at least two of the clause's word stems
    (:func:`_word_stems`) occur in that sentence, and the clause adds at most one stem of its own. "Household borrowing fell
    sharply during 2023. Since households borrowed less, the rate rise reduced consumer spending.": the second sentence
    concludes from the first, so it rests on it. A reason clause that brings a reason of its own draws nothing from the
    sentence before it: "The treaty weakened the republic. Because it imposed heavy reparations, the government faced a
    crisis."; "Germany resented the treaty. Since the treaty took territory from Germany, ..." (repair round 2,
    NAME-LINK-NONDISCRIMINATING: the text delivery then reads the argument as a structured report does). A sentence that
    opens with no reason clause concludes from an earlier one when it opens with a ground phrase pointing back to it
    (:func:`grounded_on_earlier`: "With turnover that high, ...")."""
    clause = leading_reason_clause(sentence)
    if clause is None:
        return grounded_on_earlier(sentence, earlier)
    mine = _word_stems(clause)
    if len(mine) < 2:
        return False
    for text in earlier:
        shared = mine & _word_stems(mask_quotations(text or ""))
        if len(shared) >= 2 and len(shared) >= len(mine) - 1:
            return True
    return False


#: Prepositions that open a phrase giving what was said before as the ground of the main clause ("With turnover that high,
#: ...", "Given these figures, ...", "Because of this, ...", "In light of that, ..."). Longer leads first.
GROUND_PHRASE_LEADS: tuple[tuple[str, ...], ...] = (
    ("as", "a", "result", "of"), ("in", "light", "of"), ("in", "view", "of"), ("because", "of"), ("owing", "to"), ("due", "to"),
    ("faced", "with"), ("given",), ("with",),
)


#: Words that point back to what was said: a demonstrative ("this", "these figures", "turnover that high"), "such" or a
#: degree "so" ("turnover so high").
_BACK_REFERENCES = frozenset({"this", "that", "these", "those", "such", "so"})


#: Back-references that, after a word of the phrase, are degree adverbs: the word after them is the degree said before
#: ("figures this stark", "turnover that high"), not a subject of its own.
_DEGREE_REFERENCES = frozenset({"this", "that", "so"})


#: Last words that make a back-reference a discourse marker, not a ground ("With that said, ...", "That aside, ...").
_MARKER_ENDS = frozenset({"said", "aside", "noted"})


#: A ground phrase is a phrase: at most this many words between the lead and its comma.
_GROUND_PHRASE_MAX_WORDS = 8


#: Nouns that name what was said in general ("these figures", "this evidence", "with this in mind"): a back-reference
#: through one of them restates the sentence before without naming its subject.
_REFERRING_NOUN_STEMS: frozenset[str] = frozenset(_word_stems(
    "figures figure numbers results findings evidence data facts points reasons factors trends levels rates changes problems "
    "conditions circumstances situation case mind argument arguments view views sources source extract statistics information "
    "considerations limitations issues"))


def grounded_on_earlier(sentence: str, earlier: Sequence[str]) -> bool:
    """Whether ``sentence`` opens with a ground phrase that points back to a sentence before it: a preposition of
    :data:`GROUND_PHRASE_LEADS`, then a phrase of at most :data:`_GROUND_PHRASE_MAX_WORDS` words holding a demonstrative or
    "such", closed by a comma a main clause follows; the phrase names nothing beyond what was said ("Given this, ...",
    "Because of these figures, ...") or shares a word stem with one of ``earlier`` ("The case study reports staff turnover
    of 23% a year. With turnover that high, staffing a third branch would be a serious risk."): the main clause is drawn
    from that sentence, as a reason clause that restates it is (:func:`concludes_from_earlier`; repair round 3, V3-H2:
    the text delivery then reads the argument as a structured report does). The word after a degree "this", "that" or
    "so" inside the phrase is the degree said before ("Given figures this stark, ..."), not a subject of its own. No ground:
    a phrase without a back-reference
    ("With the war over, ..."), a discourse marker ("With that said, ..."), a bare "With that," or "With this," (a time:
    'thereupon'), a phrase that names something no earlier sentence mentions ("Because of this law, ..." after sentences
    about prices). Quotations are masked; linear in the sentence."""
    head = mask_quotations(sentence[: _REASON_CLAUSE_MAX + 200]) if sentence else ""
    spans = lexis.token_spans(head)
    if not spans or head[: spans[0][0]].strip(" \t\"'“”‘’([*_-"):
        return False
    toks = [t for _s, _e, t in spans]
    lead = next((cue for cue in GROUND_PHRASE_LEADS if tuple(toks[: len(cue)]) == cue), None)
    if lead is None or (lead == ("given",) and len(toks) > 1 and toks[1] == "that"):
        return False  # "Given that ..." opens a reason clause (leading_reason_clause), never a phrase
    start = spans[len(lead) - 1][1]
    comma = head.find(",", start, _REASON_CLAUSE_MAX)
    if comma < 0 or not any(c.isalpha() for c in head[comma + 1:]):
        return False
    phrase = [t for s, _e, t in spans[len(lead):] if s < comma]
    if not phrase or len(phrase) > _GROUND_PHRASE_MAX_WORDS or not _BACK_REFERENCES.intersection(phrase):
        return False
    if phrase[-1] in _MARKER_ENDS or (lead == ("with",) and len(phrase) < 2):
        return False
    degree = {phrase[k + 1] for k in range(1, len(phrase) - 1) if phrase[k] in _DEGREE_REFERENCES}
    named = _word_stems(head[start:comma]) - _REFERRING_NOUN_STEMS - _word_stems(" ".join(degree))
    if not named:
        return True
    return any(named & _word_stems(mask_quotations(text or "")) for text in earlier)


#: Evidential leads that open a conclusion drawn from the sentence before ("This shows that B.", "These figures suggest that B.").
_EVIDENTIAL_LEAD_RE = re.compile(
    r"^\W*(?:this|that|these|those|it|which)(?:\s+[a-z’'-]+){0,2}\s+(?:shows?|showed|suggests?|suggested|proves?|proved|demonstrates?|demonstrated"
    r"|indicates?|indicated|implies|implied|means|meant|confirms?|confirmed)\s+(?:that\s+)?\w", re.IGNORECASE)


def opens_with_conclusion(sentence: str) -> bool:
    """Whether ``sentence`` (quotations masked) opens with a conclusion lead ("So ...", "Therefore ...", "As a result ...",
    "It follows that ...", "This shows that ...", "These figures suggest that ..."): it draws its conclusion from what stands
    before it. "So far ...", "So many ..." are no lead."""
    head = mask_quotations(sentence[:400]) if sentence else ""
    if _EVIDENTIAL_LEAD_RE.match(head):
        return True
    spans = lexis.token_spans(head)
    if not spans or head[: spans[0][0]].strip(" \t\"'“”‘’([*_-"):
        return False
    toks = [w for _a, _b, w in spans]
    for cue in CONCLUSION_LEADS:
        if tuple(toks[: len(cue)]) == cue:
            return not (cue == ("so",) and len(toks) > 1 and toks[1] in _SO_NOT_CONNECTIVE) and _clause_words(spans[len(cue):]) >= _MIN_CLAUSE_WORDS
    return False
