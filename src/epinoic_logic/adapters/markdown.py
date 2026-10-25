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
import itertools
import json
import re
from typing import Iterator, Optional, Sequence

from .. import lexis

__all__ = [
    "BOM", "MAX_CLAIM_TEXT_CHARS", "LIST_MARKER_RE", "LIST_LINE_RE", "HEADING_LINE_RE", "FENCE_BLOCK_RE", "FENCE_LINE_RE",
    "EMPHASIS_RE", "MEMORY_LABEL_RE", "SELF_CERT_RE", "is_word_count_line", "TASK_NOTE_RE", "DOUBLE_QUOTE_MARKS", "JSON_BLOCK_RE", "JSON_KEY_RE",
    "DOUBLE_QUOTE_SPAN_RE", "SINGLE_QUOTE_SPAN_RE",
    "strip_markup", "strip_json_blocks", "split_list_items", "truncate_claim_text", "is_memory_label", "is_self_certification",
    "is_note_sentence", "is_task_note", "split_note_clauses", "unbalanced_double_quotes", "normalize_double_marks",
    "dangling_quote_offset", "undelimited_quote_span", "undelimited_quote_spans", "find_quotation_spans", "is_json_block", "is_json_shaped",
    "find_json_spans", "mask_json_spans", "split_json_spans", "LEADING_MEMORY_LABEL_RE", "INLINE_MEMORY_LABEL_RE",
    "bracket_match_ends", "mask_quotations", "LABEL_PHRASE_RE", "is_provenance_note", "is_label_quotation", "is_peer_attribution",
    "PEER_ATTRIBUTION_RE", "NOTE_LEAD_RE", "QUOTATION_ROLES", "quotation_role", "cited_quotation_spans", "uncited_quotation_spans",
    "FEEDBACK_TASK_RE", "corrections_apply", "quotation_task", "feedback_task", "in_quotation_task", "MENTION_FUNCTION_WORDS", "MENTION_CONNECTIVES", "REASON_LEADS", "leading_reason_clause", "concludes_from_earlier",
    "CONCLUSION_LEADS", "opens_with_conclusion", "states_own_reason", "GROUND_PHRASE_LEADS", "grounded_on_earlier",
]

BOM = "\ufeff"
MAX_CLAIM_TEXT_CHARS = 4000
#: A list marker at the start of a line: ``1.``, ``2)``, ``-``, ``*``, ``•``, ``–``.
LIST_MARKER_RE = re.compile(r"^[ \t]*(?:\(?\d{1,3}[.)]|[-*•–—])[ \t]+")
LIST_LINE_RE = re.compile(r"\n(?=[ \t]*(?:\(?\d{1,3}[.)]|[-*•–—])[ \t]+)")
HEADING_LINE_RE = re.compile(r"^[ \t]*#{1,6}[ \t]+.*$", re.MULTILINE)
#: A paired code fence and everything inside it. Fenced code, a pasted receipt or a decoration (a footer, a table dump) is
#: not argument prose and is removed whole; a fence of prose keeps its body (:func:`strip_markup`).
FENCE_BLOCK_RE = re.compile(r"^[ \t]*(```|~~~)[^\n]*\n.*?^[ \t]*\1[ \t]*$", re.MULTILINE | re.DOTALL)
#: A stray (unpaired) fence line.
FENCE_LINE_RE = re.compile(r"^[ \t]*(?:```|~~~).*$", re.MULTILINE)
#: The same paired fence with its info string and body captured (:func:`strip_markup` keeps a prose body).
_FENCE_PARTS_RE = re.compile(r"^[ \t]*(```|~~~)[ \t]*([^\n]*)\n(.*?)^[ \t]*\1[ \t]*$", re.MULTILINE | re.DOTALL)
#: Info strings under which a fenced body may be the writer's prose (no language, or a text or markdown tag).
_PROSE_FENCE_TAGS = frozenset({"", "text", "txt", "markdown", "md", "plain", "plaintext", "prose"})
_FENCE_SENTENCE_END_RE = re.compile(r"[.!?][\"”’')\]]*(?=\s|$)")
#: A fenced body is prose when it has at least this many words and two sentence ends.
_MIN_FENCED_PROSE_WORDS = 20
#: Emphasis markers must stand at word boundaries: ``_emphasis_`` is markup, but the
#: underscores of ``receipt_id`` or ``Reichsbank_crisis`` are part of the word and stay.
EMPHASIS_RE = re.compile(r"(?<!\w)(\*\*|__|\*|_|`)(?=\S)(.+?)(?<=\S)\1(?!\w)")
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
#: without crossing a blank line: machine output pasted into the answer.
JSON_BLOCK_RE = re.compile(r"^[ \t]*[\[{](?:[^\n]|\n(?![ \t]*\n))*?[\]}][ \t]*$", re.MULTILINE)

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
#: The answer's own items, including its working (calculations, computations, workings, derivations: repair round 2,
#: combinator-faults-3 variant "All of the calculations above were confirmed correct by the verification engine").
_ITEMS = (r"(?:figures?|dates?|quotations?|quotes?|claims?|statistics?|numbers?|statements?|facts?|citations?|references?|calculations?|computations?"
          r"|workings?|derivations?)")
#: Every item of the answer: "every figure", "all of these figures", "each one of the quotations", "every date and figure in this paragraph".
_EVERY_ITEM = (rf"(?:every|each|all)(?: one)?(?: of (?:the|these|those|my|our|its))? {_ITEMS}(?:,? (?:and|or) {_ITEMS})*"
               rf"(?: (?:in|of|from) (?:this|the) (?:paragraph|answer|response|text|essay|above))?")
#: The answer's items located in the answer itself: "the figures here", "these dates above", "the quotations given here".
_ANCHORED_ITEMS = (rf"(?:the|these|those|my|our|all the|all these) {_ITEMS}(?:,? (?:and|or) {_ITEMS})*"
                   r" (?:here|above|below|(?:given|cited|stated|quoted|used) (?:here|above|below)|in this (?:paragraph|answer|response|essay|text))")
_COPULA = r"(?:is|are|was|were|has been|have been|has now been|have now been)\s+(?:all\s+|fully\s+|carefully\s+|now\s+|independently\s+)?"
#: The verification infrastructure itself (an agent claiming that the engine, the solver or the hub already passed its answer).
_INFRASTRUCTURE = (r"(?:\bz3\b|\b(?:the\s+|an?\s+)?(?:(?:automated|automatic|verification|logic|formal|z3|translation|integrity|proof|symbolic)\s+)?"
                   r"(?:engine|solver|verifier|checker|prover|validator)\b"
                   r"|\b(?:the\s+)?(?:verification|integrity|formal)\s+(?:checks?|layer|pipeline)\b|\bthe\s+(?:hub|channel|translator|overseer|router|combinator)\b)")
#: The checking words of an elliptical status credited to the infrastructure ("Checked and signed off by the overseer.").
_ELLIPTIC_CHECK = r"(?:checked|verified|confirmed|validated|approved|certified|reviewed|proof[- ]?read|audited|signed\s++off|cleared|passed)"
#: Verification-status vocabulary in the body: an agent certifying its own output or
#: imitating a channel receipt. Status words count only in capitals (a vote that "was
#: accepted" is history, not a receipt); phrases are matched case-insensitively. The
#: self-referential forms ("every figure in this paragraph is accurate", "all of the above
#: has been cross-checked") require the subject to be the answer itself or its items,
#: immediately followed by a copula and a checking or accuracy word, and no digit in the
#: span, so that an argument about what a court "is correct" to do is not a self-report.
SELF_CERT_RE = re.compile(
    r"\b(?:VERIFIED|ACCEPTED_WITH_FINDINGS|ACCEPTED|REJECTED|ENTAILED|COUNTEREXAMPLE|INCONSISTENT_PREMISES)\b"
    r"|(?i:\ball (?:claims|dates|figures|facts|quotations|steps|calculations|computations|workings|results|values|answers)(?: and (?:figures|dates|quotations|steps))?"
    r"(?: (?:have been|were|are|was|is))? ?(?:checked|verified|confirmed|validated)\b"
    # a sentence that is nothing but a check's outcome ("Formally verified ✓", "Checked.", "All verified!") or a status line
    # opening a sentence ("Status: VALID.", "Status — passed"): repair round 4, rerun-combinator-faults-3 variant; a
    # "Result:" or "Outcome:" line is the answer's content and is none
    r"|(?:^|(?<=[.!?;:]))\s*+(?:(?:formally|fully|independently|automatically|mathematically|logically|rigorously|all|everything|every\s++step|each\s++step)\s++)?"
    r"(?:verified|checked|validated|certified|approved|confirmed)\s*+[✓✔☑✅]*+\s*+[.!]?+\s*+$"
    # the same outcome as a sentence of its own in brackets, its full stop inside ("(Verified.)"; an aside "12 (checked)" in
    # a sentence is read as before)
    r"|^\s*+[(\[]\s*+(?:(?:formally|fully|independently|all|everything)\s++)?(?:verified|checked|validated|certified|approved|confirmed)\s*+[✓✔☑✅]*+\s*+[.!]\s*+[)\]]\s*+[.!]?+\s*+$"
    # repair round 5, rerun-combinator-faults-3 variant: a check mark with a verdict ("✔ All correct.", "All correct ✓"), an
    # elliptical status credited to the infrastructure ("Checked and signed off by the overseer."), a guarantee of the
    # answer's accuracy ("Accuracy guaranteed.", "100% accurate."), a result line that is only a verdict ("Result: correct.";
    # "Result: the firm should expand." is content), and the answer as a whole reviewed and approved with no agent ("This
    # has been peer-reviewed and approved.")
    r"|(?:^|(?<=[.!?;:]))\s*+(?:[(\[]\s*+)?[✓✔☑✅]++\s*+(?:(?:all|everything|fully|100\s*+%)\s++)?(?:(?:is|are)\s++)?(?:correct|accurate|right|valid|verified|checked|passed|approved|confirmed|ok|okay|good|done"
    r"|fine|in\s++order|checks?\s++out)"
    r"\s*+[.!]?+\s*+[)\]]?+\s*+[.!]?+\s*+$"
    r"|(?:^|(?<=[.!?;:]))\s*+(?:(?:all|everything|fully)\s++)?(?:correct|accurate|right|ok|okay|good|verified|checked)\s*+[✓✔☑✅]++\s*+[.!]?+\s*+$"
    # (the list of checking words is read as words and separators, each consumed once, so a whitespace run is linear; a comma, or
    # "and" with a run of two or more blanks, may still stand right before "by", as it could before)
    rf"|(?:^|(?<=[.!?;:]))\s*+{_ELLIPTIC_CHECK}(?:(?:\s*+,\s*+|\s++and\s++)?+{_ELLIPTIC_CHECK})*+(?:\s*+,|\s++and(?=\s\s))?+"
    r"\s++by\s++(?:the\s++)?(?:z3|engine|solver|verifier|checker|translator|overseer|hub|router|channel|combinator|integrity\s++layer|verification\s++(?:engine|layer|pipeline))\b"
    r"|(?:^|(?<=[.!?;:]))\s*+(?:(?:accuracy|correctness|validity|quality)(?:\s++(?:is|fully))?\s++(?:guaranteed|assured|certified)"
    r"|(?:guaranteed|certified)\s++(?:100\s*+%\s++)?(?:accurate|correct|error[- ]free)|100\s*+%\s++(?:accurate|correct|verified|error[- ]free))\s*+[.!]?+\s*+$"
    r"|(?:^|(?<=[.!?;:]))\s*+(?:result|outcome|answer\s++check)(?:\s*+(?:[:=]|[—–])|\s++-(?=\s))\s*+(?:correct|verified|checked|confirmed|passed|approved|accurate|ok|okay|[✓✔✅])\s*+[.!]?+\s*+$"
    r"|(?:^|(?<=[.!?;:]))\s*+(?:this|everything(?:\s++(?:here|above))?|all\s++of\s++(?:this|the\s++above))\s++(?:has|have)\s++(?:now\s++)?been\s++(?:(?:fully|independently|thoroughly|carefully|formally)\s++)?"
    r"(?:peer[- ]reviewed|reviewed|checked|verified|validated|fact[- ]checked|proof[- ]?read|audited)\s++and\s++(?:approved|signed\s++off|verified|confirmed|certified|validated|cleared)\s*+[.!]?+\s*+$"
    r"|(?:^|(?<=[.!?;:]))\s*+status(?:\s*+(?:[:=]|[—–])|\s++-(?=\s))\s*+(?:valid|passed|pass|approved|confirmed|correct|checked|complete|completed"
    r"|success|successful|clear|verified|ok|okay|[✓✔])(?![\w-])"
    r"|\b(?:verified|checked|confirmed|validated|proved|proven|accepted|certified|approved) by (?:the )?(?:(?:verification|logic|formal|z3) )?(?:z3|engine|solver|verifier|translator|overseer|hub)\b"
    r"|\bfact[- ]?checked\b|\bself[- ]?certif\w*|\bverification (?:complete|passed|status)\b|\bchecked and confirmed\b"
    r"|\bdouble[- ]checked\b|\bcross[- ]checked\b|\bcompared (?:with|against) the supplied\b|\bmatch(?:es|ed)? (?:it|them) exactly\b"
    r"|\bno findings\b|\bfindings:\s*none\b|\btransmission (?:accepted|rejected)\b|\bvia branch \w+\b|\bstatus:\s*(?:entailed|accepted|rejected|verified|ok)\b"
    # a status line, a label and its outcome: "Verification: passed.", "Checks: OK", "Self-check — complete" (repair round 2,
    # combinator-faults-3 variant); the label is the checking itself, so "Results: positive" or "Conclusion: valid" is none
    r"|\b(?:verification|validation|self[- ]check|(?:formal\s++|automated\s++)?checks?|check\s++results?|proof\s++check|z3|qa|q\.a\.|quality(?:\s++(?:assurance|control|checks?))?"
    r"|(?:peer\s++)?review|audit|accuracy(?:\s++checks?)?|fact[- ]checks?|fact[- ]checking)(?:\s*+(?:[:=]|[—–])|\s++-(?=\s))\s*+"
    r"(?:passed|pass|ok|okay|complete|completed|successful|success|succeeded|verified|confirmed|done|all\s++clear|clear|✓|✔)(?![\w-])"
    # the checks themselves as what passed, opening a sentence or following a colon ("All checks passed.", "Verified: every
    # check passes", "No checks failed."): the status of the answer's checks (repair round 1, re-run review cf-3 variant);
    # "if all checks pass, the record is saved" (a program's checks, inside a clause) is no status
    r"|(?:^|(?<=[:;!?.]))\s*+(?:and\s++)?(?:all|every|each)(?:\s++one)?(?:\s++of)?(?:\s++(?:the|these|its|my|our))?\s++(?:(?:formal|verification|automated|integrity|engine|solver|logic)\s++)?checks?"
    r"\s++(?:(?:have|has)\s++)?(?:all\s++)?(?:passed|pass|passes|succeeded)\b"
    r"|(?:^|(?<=[:;!?.]))\s*+no\s++(?:(?:formal|verification|automated|integrity)\s++)?checks?\s++(?:(?:have|has)\s++)?failed\b"
    r"|(?:\"|\b)(?:status|receipt_id|transmission_id|formal_checks|structural_findings|findings|codes)\"\s*:"
    rf"|\b{_ANSWER_ITSELF}(?: (?:is|are|was|were|has been|have been)|,? (?:which|and) (?:is|are|has been|have been))\s+(?:all\s+|fully\s+|carefully\s+|now\s+)?{_CHECK_WORDS}\b"
    # the answer itself as what passed the checks, its subject right before the verb ("This answer has passed every quality
    # check", "The above cleared all the checks"): repair round 4, rerun-combinator-faults-3 variant; a quantifier is needed,
    # so "passed the test of time" is none, and a passing the answer reports of something else ("This essay argues that the
    # policy passed every test") is no self-report
    rf"|\b{_ANSWER_ITSELF}\s++(?:has\s++|have\s++|had\s++)?(?:now\s++|already\s++|successfully\s++|also\s++)?(?:passed|cleared|survived|satisfied)\s++"
    r"(?:every|each|all(?:\s++(?:of\s++)?(?:the|its|these|our|my))?)\s++(?:[\w-]++\s++){0,2}?(?:checks?|tests?|reviews?|audits?|inspections?|validations?|verifications?)\b"
    rf"|\b{_EVERY_ITEM}\s+{_COPULA}{_CHECK_WORDS}\b"
    # the writer certifying a figure against an outside record: "a figure I have verified against the national statistics
    # office", "I checked it against the census", "we confirmed it with the ministry"; and the answer's own items checked
    # the same way, "this figure was checked against the ONS release". A check credited to someone else ("the theory was
    # verified against experiment", "historians have confirmed with archival evidence") is an argument, not a self-report.
    rf"|\b(?:I|we)(?:\s++have|['’]ve|\s++had)?\s++(?:(?:now|also|personally|carefully|independently|already|just|thoroughly|myself|ourselves)\s++)*+"
    rf"(?:verified|checked|confirmed|validated|double[- ]checked|cross[- ]checked)\s++(?:(?:it|this|these|them|that|those|each\s++one|(?:the|this|that|these|those|each|every|my|our|all\s+the)\s+(?:figure|figures|date|dates|number|numbers|value|values|data|statistic|statistics|quotation|quotations|total|totals))\s++)?(?:against|with)\b"
    rf"|\b(?:this|that|these|those|each|every|my|our|the\s++above)\s++(?:figure|date|number|statistic|value|quotation|quote|total|estimate)s?\s++"
    rf"(?:was|were|is|are|has\s++been|have\s++been)\s++(?:(?:all|now|also|carefully|independently)\s++)?(?:verified|checked|confirmed|cross[- ]checked|double[- ]checked)\s++(?:against|with)\b)",
)
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
    r"|\bno (?:errors?|mistakes?|inaccuracies|problems)\s+(?:were|was|have been|has been|are|is)\s+(?:found|detected|identified|present)\b"
    # proven or certified correct, or checked by a named method ("has been mathematically proven correct", "certified",
    # "formally verified"): repair round 2, combinator-faults-3 variant
    r"|\b(?:prov(?:ed|en)|certified|demonstrated|shown)\s+(?:to\s+be\s+)?(?:correct|accurate|valid|right|sound|true|error[- ]free)\b|\bcertified\b"
    r"|\b(?:mathematically|formally|logically|rigorously|automatically|computationally)\s+(?:prov(?:ed|en)|verified|checked|certified|validated|confirmed)\b",
    re.IGNORECASE,
)
#: A checking predicate under negation or a deontic modal: the words just before it make it a disclaimer.
_NEGATED_OR_DEONTIC_RE = re.compile(
    r"(?:\bnot|\bnever|n['’]t|\bcannot|\bno longer|\byet to|\bstill to)\s+(?:\w+\s+){0,3}$"
    r"|\b(?:should|must|needs?\s+to|ought\s+to|has\s+to|have\s+to|had\s+to|are\s+to|is\s+to|to)\s+(?:(?:still|first|all|each|independently|carefully|also|then|now)\s+)*(?:have\s+)?(?:be|been)\s+(?:\w+ly\s+)?$",
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
               r"|calculations?|computations?|workings?|derivations?|steps?"
               r"|totals?|estimates?|details?|items?|(?:quoted|cited) lines?)")
#: The items whose accuracy a bare adjective can certify ("these figures are accurate"); "these claims are reliable" may be
#: a historian weighing a source, so claims, statements, facts and details need a checking predicate instead.
_ACC_ITEM_RE = re.compile(r"(?:figures?|dates?|quotations?|quotes?|statistics?|numbers?|citations?|references?|excerpts?|totals?|(?:quoted|cited) lines?)\W*$",
                          re.IGNORECASE)
#: Up to two plain modifiers between a determiner and an item noun ("every mileage figure", "the key dates"); a modifier is
#: never a verb, an auxiliary, a preposition, a conjunction or an anchor word.
_SELF_MOD_STOP = (r"(?:is|are|was|were|has|have|had|been|be|being|and|or|but|nor|of|in|on|at|to|for|from|with|by|that|which|who|here"
                  r"|above|below|given|not|no|as|than|so|its|it|this|these|those|the|a|an)\b")
_SELF_MOD = rf"(?:(?!{_SELF_MOD_STOP})[a-z][a-z'’-]*\s+){{0,2}}"
#: Where the answer locates its own items: "here", "above", "given above", "in this answer", "of the paragraph above".
_SELF_ANCHOR = (r"(?:here|above|below|(?:given|cited|stated|quoted|used|listed|presented|included|offered|mentioned|provided|reproduced|set out)"
                r"\s+(?:here|above|below|in\s+(?:this|my|the)\s+(?:paragraph|answer|response|essay|analysis|outline|summary))"
                r"|in\s+(?:this|my)\s+(?:paragraph|answer|response|essay|analysis|outline|summary|report)|(?:in|of)\s+the\s+(?:paragraph|answer|response|essay)\s+above)")
def _item_list(mod: str) -> str:
    """Items with their modifiers ``mod``, listed with 'and' or 'or'."""
    return rf"{mod}{_SELF_ITEMS}(?:,?\s+(?:and|or)\s+{mod}{_SELF_ITEMS})*"


_SELF_ITEM_LIST = _item_list(_SELF_MOD)
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
def _sourced(mod: str) -> str:
    return (rf"(?:{_SELF_UNIVERSAL_DET}\s+|(?:the|these|those|my|our)\s+)?"
            rf"(?:{_item_list(mod)}\s+{_SOURCE_LINK}\s+{_SOURCE_REPORT}|{mod}{_QUOTE_ITEMS}\s+{_SOURCE_LINK}\s+(?:{_SOURCE_REPORT}|{_SOURCE_TEXT}))"
            rf"(?:\s+{_SELF_ANCHOR})?")


_SELF_SOURCED = _sourced(_SELF_MOD)
#: Items named with their source, read in a pass of their own (:func:`_structural_self_report`) and only when the sentence
#: names a source after "of" or "from" (:data:`_SOURCE_CUE_RE`), so the subject scan of every other sentence costs what it did.
_SELF_SOURCED_RE = re.compile(rf"\b(?P<sourced>{_SELF_SOURCED})\b", re.IGNORECASE)
_SOURCE_CUE_RE = re.compile(r"\b(?:of|from)\s+(?:\w+\s+){0,3}?(?:specialist|colleague|peer|report|account|paragraph|answer|poems?|sonnet|texts?|extracts?"
                            r"|passages?|novel|play|story|documents?)\b", re.IGNORECASE)
#: One subject, by kind: anchored items, the answer itself, every item, demonstrative items ("these figures", "my
#: quotations") and bare definite items ("the quotations"). The kind decides which predicates certify
#: (:func:`_structural_self_report`).
def _subject_kinds(mod: str) -> str:
    item_list = _item_list(mod)
    return (rf"\b(?:(?P<anchored>(?:{_SELF_UNIVERSAL_DET}\s+|(?:the|these|those|my|our)\s+)?{item_list}\s+{_SELF_ANCHOR})"
            rf"|(?P<answer>{_SELF_ANSWER})"
            rf"|(?P<universal>{_SELF_UNIVERSAL_DET}\s+{item_list})"
            rf"|(?P<demonstrative>(?:these|those|my|our)\s+{item_list})"
            rf"|(?P<definite>the\s+{item_list}))\b")


_SELF_SUBJECT_KINDS_RE = re.compile(_subject_kinds(_SELF_MOD), re.IGNORECASE)

# ---- the subject scans, read in linear time (security round 2) -----------------------------------------------------------
# ``_SELF_SUBJECT_KINDS_RE`` and ``_SELF_SOURCED_RE`` were scanned with ``finditer``, which tries a match at every place of
# the sentence. A try that starts inside a long list of items ('statistics or x statistics or x statistics ...') reads the
# list to its end before it fails for want of an anchor or a source after it, and so does the try at every later item, and
# at every letter after an apostrophe or a hyphen of a long run such as "'b'b'b...": quadratic in the list or the run. The
# readers below try the patterns only where a match can start, decided from a reading of the sentence made once: where the
# item nouns stand (every subject but the answer itself holds one, at most six runs of characters after its start), where
# each item a list may hold ends, which item follows a list's 'and' or 'or', and whether a list from an item's end reaches
# an anchor or a source. The pattern itself gives each match (its span, its kind and its groups).
_DET_OF = r"(?:the|these|those|my|our|its)"
#: Every form :data:`_SELF_UNIVERSAL_DET` takes (each of its optional parts taken or left), and the other determiners of the
#: subjects, each with the white space after it.
_DET_FORM_RES = tuple(re.compile(rf"{d}\s+", re.IGNORECASE) for d in (
    "every", "each", r"each\s+one", rf"each\s+of\s+{_DET_OF}", rf"each\s+one\s+of\s+{_DET_OF}", "all", rf"all\s+{_DET_OF}",
    rf"all\s+of\s+{_DET_OF}", r"(?:the|these|those|my|our)"))
#: An item noun of a subject (the quotation nouns of a sourced subject included); the runs of characters between white
#: space; the places a word starts; the first words of the answer itself (:data:`_SELF_ANSWER`).
_SUBJECT_NOUN_RE = re.compile(rf"\b(?:{_SELF_ITEMS}|{_QUOTE_ITEMS})\b", re.IGNORECASE)
_RUN_OF_CHARS_RE = re.compile(r"\S+")
_WORD_START_RE = re.compile(r"\b\w")
_ANSWER_FIRST_RE = re.compile(r"\b(?:this|all|the|everything|my|our)\b", re.IGNORECASE)
#: A subject starts at most this many runs of characters before the run its first item noun starts in: four of a
#: determiner ('each one of the') and two modifiers.
_SUBJECT_LEAD_RUNS = 6
_LETTER_RE = re.compile(r"[a-z]", re.IGNORECASE)
_MOD_RUNS_RE = re.compile(r"[a-z'’-]+", re.IGNORECASE)
_MOD_STOP_RE = re.compile(_SELF_MOD_STOP, re.IGNORECASE)
_ONE_MOD = rf"(?!{_SELF_MOD_STOP})[a-z][a-z'’-]*\s+"
#: An item noun where an item starts, and after a first modifier's run of letters: white space, then no further modifier
#: or one, then the noun. A noun ends where a word ends: a list goes on, an anchor or a source follows, or the subject
#: ends only there.
_ITEM_WORD_RE = re.compile(rf"{_SELF_ITEMS}\b", re.IGNORECASE)
_ITEM_REST_RES = (re.compile(rf"\s+{_SELF_ITEMS}\b", re.IGNORECASE), re.compile(rf"\s+{_ONE_MOD}{_SELF_ITEMS}\b", re.IGNORECASE))
_LIST_SEP_RE = re.compile(r",?\s+(?:and|or)\s+", re.IGNORECASE)
_ANCHOR_AFTER_RE = re.compile(rf"\s+{_SELF_ANCHOR}\b", re.IGNORECASE)
_SOURCE_AFTER_RE = re.compile(rf"\s+{_SOURCE_LINK}\s+{_SOURCE_REPORT}(?:\s+{_SELF_ANCHOR})?\b", re.IGNORECASE)
_QUOTE_TAIL = rf"{_QUOTE_ITEMS}\s+{_SOURCE_LINK}\s+(?:{_SOURCE_REPORT}|{_SOURCE_TEXT})(?:\s+{_SELF_ANCHOR})?\b"
_QUOTE_HEAD_RE = re.compile(_QUOTE_TAIL, re.IGNORECASE)
_QUOTE_REST_RES = (re.compile(rf"\s+{_QUOTE_TAIL}", re.IGNORECASE), re.compile(rf"\s+{_ONE_MOD}{_QUOTE_TAIL}", re.IGNORECASE))
_ANSWER_AT_RE = re.compile(rf"(?:{_SELF_ANSWER})\b", re.IGNORECASE)


class _SubjectReading:
    """What the subject scans read of one sentence, each part once: the runs of letters, apostrophes and hyphens a modifier
    reads, the ends of the items that start at each place, and whether a list from an item's end reaches an anchor
    (``'anchor'``) or a source (``'source'``)."""

    __slots__ = ("text", "_runs", "_items", "_rest", "_quote_rest", "_reach")

    def __init__(self, text: str) -> None:
        self.text = text
        self._runs: Optional[tuple[list[int], list[int]]] = None
        self._items: dict[int, tuple[int, ...]] = {}
        self._rest: dict[int, tuple[int, ...]] = {}
        self._quote_rest: dict[int, bool] = {}
        self._reach: dict[str, dict[int, bool]] = {"anchor": {}, "source": {}}

    def _first_mod_end(self, s: int) -> int:
        """The end of the run a first modifier reads from ``s`` (-1 when no modifier starts there)."""
        text = self.text
        if not _LETTER_RE.match(text, s) or _MOD_STOP_RE.match(text, s):
            return -1
        if self._runs is None:
            starts, ends = [], []
            for m in _MOD_RUNS_RE.finditer(text):
                starts.append(m.start())
                ends.append(m.end())
            self._runs = (starts, ends)
        starts, ends = self._runs
        i = bisect.bisect_right(starts, s) - 1
        return ends[i] if i >= 0 and ends[i] > s else -1

    def item_ends(self, s: int) -> tuple[int, ...]:
        """Where an item that starts at ``s`` may end: its noun right there, or after one or two modifiers."""
        got = self._items.get(s)
        if got is None:
            ends = []
            m = _ITEM_WORD_RE.match(self.text, s)
            if m is not None:
                ends.append(m.end())
            r = self._first_mod_end(s)
            if r >= 0:
                rest = self._rest.get(r)
                if rest is None:
                    rest = self._rest[r] = tuple(x.end() for x in (rx.match(self.text, r) for rx in _ITEM_REST_RES) if x is not None)
                ends.extend(rest)
            got = self._items[s] = tuple(ends)
        return got

    def quote_head(self, s: int) -> bool:
        """Whether a quotation item and its source start at ``s`` (the second form of :data:`_SELF_SOURCED`)."""
        if _QUOTE_HEAD_RE.match(self.text, s):
            return True
        r = self._first_mod_end(s)
        if r < 0:
            return False
        got = self._quote_rest.get(r)
        if got is None:
            got = self._quote_rest[r] = any(rx.match(self.text, r) for rx in _QUOTE_REST_RES)
        return got

    def reaches(self, e: int, kind: str) -> bool:
        """Whether a list whose item ends at ``e`` goes on, item by item, to an end that an anchor (``'anchor'``) or a source
        (``'source'``) follows."""
        memo = self._reach[kind]
        after = _ANCHOR_AFTER_RE if kind == "anchor" else _SOURCE_AFTER_RE
        stack = [e]
        while stack:
            x = stack[-1]
            if x in memo:
                stack.pop()
                continue
            if after.match(self.text, x):
                memo[x] = True
                stack.pop()
                continue
            sep = _LIST_SEP_RE.match(self.text, x)
            nxt = self.item_ends(sep.end()) if sep is not None else ()
            todo = [y for y in nxt if y not in memo]
            if todo:
                stack.extend(todo)
                continue
            memo[x] = any(memo[y] for y in nxt)
            stack.pop()
        return memo[e]

    def det_heads(self, q: int) -> list[int]:
        """Where the items start after each determiner form that starts at ``q``."""
        return [m.end() for m in (rx.match(self.text, q) for rx in _DET_FORM_RES) if m is not None]


def _subject_starts(text: str, answer: bool) -> list[tuple[int, bool]]:
    """``(place, near_noun)`` for every place a subject may start, in order: each place a word starts in the run of
    characters of an item noun or in the six runs before it (``near_noun``), and, with ``answer``, the first word of the
    answer itself named anywhere else."""
    nouns = [m.start() for m in _SUBJECT_NOUN_RE.finditer(text)]
    firsts = [m.start() for m in _ANSWER_FIRST_RE.finditer(text)] if answer else []
    if not nouns and not firsts:
        return []
    out: dict[int, bool] = {q: False for q in firsts}
    if nouns:
        runs = [m.start() for m in _RUN_OF_CHARS_RE.finditer(text)]
        words = [m.start() for m in _WORD_START_RE.finditer(text)]
        lo_done = -1
        for p in nouns:
            j = bisect.bisect_right(runs, p) - 1
            lo = max(runs[max(0, j - _SUBJECT_LEAD_RUNS)], lo_done + 1)
            for k in range(bisect.bisect_left(words, lo), bisect.bisect_right(words, p)):
                out[words[k]] = True
            lo_done = max(lo_done, p)
    return sorted(out.items())


def _subject_may_start(reading: _SubjectReading, q: int, near_noun: bool) -> bool:
    """Whether :data:`_SELF_SUBJECT_KINDS_RE` can match at ``q``: a determiner and an item (every, demonstrative or definite
    items, which need nothing after them), items that reach an anchor, or the answer itself."""
    if near_noun:
        if any(reading.item_ends(s) for s in reading.det_heads(q)):
            return True
        if any(reading.reaches(e, "anchor") for e in reading.item_ends(q)):
            return True
    return _ANSWER_AT_RE.match(reading.text, q) is not None


def _sourced_may_start(reading: _SubjectReading, q: int, near_noun: bool) -> bool:
    """Whether :data:`_SELF_SOURCED_RE` can match at ``q``: items (after a determiner or not) that reach a source, or a
    quotation item and its source."""
    for s in (q, *reading.det_heads(q)):
        if any(reading.reaches(e, "source") for e in reading.item_ends(s)) or reading.quote_head(s):
            return True
    return False


def _subject_matches(pattern: "re.Pattern[str]", may_start, answer: bool, text: str) -> Iterator["re.Match[str]"]:
    """Every match of ``pattern`` in ``text``, the ones ``pattern.finditer(text)`` yields (spans and groups), in time linear in
    the text: ``pattern`` is tried, in order, only at the places a subject may start (:func:`_subject_starts`) where
    ``may_start`` says it can match, from the end of the last match on."""
    starts = _subject_starts(text, answer)
    if not starts:
        return
    reading = _SubjectReading(text)
    pos = 0
    for q, near_noun in starts:
        if q < pos or not may_start(reading, q, near_noun):
            continue
        m = pattern.match(text, q)
        if m is not None:
            yield m
            pos = m.end() if m.end() > m.start() else m.end() + 1


def _self_subjects(sentence: str) -> Iterator["re.Match[str]"]:
    """``_SELF_SUBJECT_KINDS_RE.finditer(sentence)``, read in linear time (:func:`_subject_matches`)."""
    return _subject_matches(_SELF_SUBJECT_KINDS_RE, _subject_may_start, True, sentence)


def _self_sourced(sentence: str) -> Iterator["re.Match[str]"]:
    """``_SELF_SOURCED_RE.finditer(sentence)``, read in linear time (:func:`_subject_matches`)."""
    return _subject_matches(_SELF_SOURCED_RE, _sourced_may_start, False, sentence)


#: What follows the subject: a copula, then adverbs, then a checking participle or an accuracy adjective.
_SELF_COPULA = r"\s+(?:is|are|was|were|(?:has|have|had)\s+(?:(?:all|each|now|both|already|also)\s+)?been|remains?)\s+"
_SELF_PERFECT_RE = re.compile(r"\s+(?:is|are|(?:has|have)\s+(?:(?:all|each|now|both|already|also)\s+)?been)\s+", re.IGNORECASE)
_SELF_ADVERBS = (r"(?:(?:all|now|fully|carefully|independently|formally|thoroughly|individually|each|already|also|both|entirely|completely"
                 r"|wholly|perfectly|properly|rigorously|systematically|duly|personally|again|mathematically|logically|automatically"
                 r"|computationally)\s+)*")
_SELF_CHECK = (r"(?:checked|verified|confirmed|validated|corroborated|audited|proof-?read|double[- ]checked|cross[- ]checked|fact[- ]checked"
               r"|re-?checked|compared\s+(?:with|against)|matched\s+(?:against|with|to)|certified"
               r"|(?:prov(?:ed|en)|demonstrated|shown)\s+(?:to\s+be\s+)?(?:correct|accurate|valid|right|sound|true|error[- ]free))")
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
_SELF_CLOSING_RE = re.compile(
    r"\s*(?:[.;!:)\]\"'”’]|$|,?\s+(?:and|so)\s+(?:can|may|might|could|need|needs|require|requires|has|have|is|are|was|were|match|matches"
    r"|appear|appears|contain|contains|so|the\s+reader)\b)",
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
#: The complement is what stands between 'against' (or 'with') and the comma: white space, then 1 to 60 characters that are
#: no comma, semicolon, colon or full stop, then white space. Read as the pattern ``\s+[^,;:.]{1,60}\s*[,:]`` it split one
#: run of white space between three quantifiers (quadratic in the run; security round 2, SEC-V4); it is read here as the same
#: set of strings, each run once: the leading run, then a core of 1 to 60 characters that starts and ends on a character that
#: is no white space (or, when the complement is white space alone, at least two white-space characters), then the trailing
#: run. Only whether the pattern matches is read (:func:`_self_certification`), and the strings it matches are the old ones.
_SELF_LEAD_RE = re.compile(
    rf"^\W*As\s+(?:(?:already|now|formally|independently|previously|carefully|fully)\s+)?"
    rf"(?:{_SELF_CHECK}|proved|proven|certified|accepted|approved)"
    r"(?:\s++(?:above|here|below|earlier|before|already|throughout|in\s+full)){0,3}"
    rf"(?:\s++by\s++{_INFRASTRUCTURE}|\s++(?:against|with)(?:\s++[^,;:.\s](?:[^,;:.]{{0,58}}[^,;:.\s])?|\s(?=\s)))?\s*+[,:]"
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
    r"(?:prov(?:ed|en|es)|verif(?:ied|ies)|confirm(?:ed|s)|accept(?:ed|s)|validat(?:ed|es)|entail(?:ed|s)|certif(?:ied|ies)|approv(?:ed|es)|signed\s+off|passed|cleared"
    # "The hub found no problems with this answer" (repair round 5, rerun-combinator-faults-3 variant)
    r"|(?:found|finds|raised|raises|reported|reports|detected|detects)\s+no\s+(?:problems?|errors?|issues?|faults?|mistakes?|findings?|objections?))\b"
    rf"|\b(?:proved|proven|verified|confirmed|accepted|validated|certified|approved|signed\s+off|passed|cleared)"
    rf"(?:\s+(?:as|to\s+be))?(?:\s+(?:correct|accurate|valid|sound|right|true|error[- ]free))?\s+by\s+{_INFRASTRUCTURE}"
    # the answer's items passing the infrastructure: "each step passed the automated checker", "cleared every formal check"
    # (repair round 2, combinator-faults-3 variant)
    rf"|\b(?:passed|passes|cleared|clears|satisfied|satisfies)\s+(?:(?:all|every|each)\s+(?:of\s+)?)?{_INFRASTRUCTURE}",
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
#: Cheap pre-filter for the structural rule: a sentence with none of these stems certifies nothing.
_SELF_CUE_RE = re.compile(
    r"check|verif|confirm|validat|corroborat|audit|proof|compar|match|accura|correct|exact|reliab|sound|right|error|faithful|verbatim|trust"
    r"|need|requir|warrant|merit|call|prov|accept|certif|approv|signed|passed|clear|entail|beyond|precis|word\s+for\s+word|letter\s+for\s+letter|without"
    r"|(?:found|finds|raised|raises|reported|reports|detected|detects)\s+no\s",
    re.IGNORECASE,
)


def strip_json_blocks(text: str) -> tuple[str, int]:
    """Remove pasted JSON blocks (a receipt, a payload) from ``text``.

    A block is removed when it opens with ``{`` or ``[`` at a line start, closes with
    the matching bracket at a line end without crossing a blank line, and either parses
    as JSON or carries a JSON key-value pair. Returns ``(text, number_removed)``.
    """
    removed = 0

    def take(m: "re.Match[str]") -> str:
        nonlocal removed
        if is_json_block(m.group(0)):
            removed += 1
            return ""
        return m.group(0)

    return JSON_BLOCK_RE.sub(take, text), removed


def _fenced_body(m: "re.Match[str]") -> str:
    """What a paired fence leaves in the text to segment: its body when the fence carries no language (or a text or
    markdown tag) and the body is prose (at least :data:`_MIN_FENCED_PROSE_WORDS` words, two sentence ends, no JSON
    shape): an answer wrapped in a fence is still the answer, as the English parser reads it. Code, a pasted receipt
    (```json ...```) and a short decoration (a footer) are removed whole."""
    info, body = m.group(2).strip().lower(), m.group(3)
    if (info in _PROSE_FENCE_TAGS and len(body.split()) >= _MIN_FENCED_PROSE_WORDS and len(_FENCE_SENTENCE_END_RE.findall(body)) >= 2
            and not JSON_KEY_RE.search(body) and not is_json_block(body.strip())):
        return body
    return ""


#: Answers up to this length keep their stripped text in a bounded cache: the channel strips one answer for several readers
#: (word bounds, paragraph counts, deliverable blocks; repair round 2, ADV2-03).
_STRIP_CACHE_MAX_CHARS = 100_000


def strip_markup(text: str) -> str:
    """Return ``text`` without a byte-order mark, CRLF, heading lines, fenced code
    blocks (fence lines and their body; a fence of prose keeps its body, :func:`_fenced_body`),
    stray fence lines, pasted JSON blocks or emphasis markers. Paragraph breaks (blank lines)
    are preserved. The caller keeps the untouched original for ``original_response``; this is
    only the text to segment. A text of at most :data:`_STRIP_CACHE_MAX_CHARS` characters is
    stripped once (a bounded cache of the pure result)."""
    if isinstance(text, str) and len(text) <= _STRIP_CACHE_MAX_CHARS:
        return _cached_strip_markup(text)
    return _strip_markup(text)


@functools.lru_cache(maxsize=64)
def _cached_strip_markup(text: str) -> str:
    return _strip_markup(text)


def _strip_markup(text: str) -> str:
    s = text.replace("\r\n", "\n").replace("\r", "\n")
    if s.startswith(BOM):
        s = s[len(BOM):]
    s = s.replace(BOM, "")
    s = HEADING_LINE_RE.sub("", s)
    s = _FENCE_PARTS_RE.sub(_fenced_body, s)
    s = FENCE_LINE_RE.sub("", s)
    s, _removed = strip_json_blocks(s)
    return _strip_emphasis(s)


#: The markers of :data:`EMPHASIS_RE`, in its order (the backtick included).
_EMPHASIS_MARKERS = ("**", "__", "*", "_", "`")


def _strip_emphasis(s: str) -> str:
    """``EMPHASIS_RE.sub(r"\\2", s)`` in linear time: ``stem.layout.emphasis_spans`` gives exactly that pattern's matches with
    these markers, reading each marker's closers once, where the pattern scans lazily to the end of the line from every
    opener that has no closer (quadratic on '`a ' repeated; parser-safety-5). Imported here, not at the top, so the two
    packages never import each other while either is being initialised."""
    from ..stem.layout import emphasis_spans
    out: list[str] = []
    pos = 0
    for start, end, b0, b1 in emphasis_spans(s, _EMPHASIS_MARKERS):
        out += [s[pos:start], s[b0:b1]]
        pos = end
    return "".join(out) + s[pos:]


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
    """Cut ``text`` to the contract limit, marking the cut with ``...``."""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def is_memory_label(sentence: str) -> bool:
    return bool(MEMORY_LABEL_RE.search(sentence))


def _positive(pattern: "re.Pattern[str]", sentence: str) -> bool:
    """True when ``pattern`` matches ``sentence`` at least once outside negation and deontic
    modals ("has not been checked", "should be checked", "must be verified" do not count)."""
    for m in pattern.finditer(sentence):
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
    sourced = _self_sourced(sentence) if _SOURCE_CUE_RE.search(sentence) else ()
    for m in itertools.chain(sourced, _self_subjects(sentence)):
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


@functools.lru_cache(maxsize=8192)
def _self_certification(sentence: str) -> bool:
    if SELF_CERT_RE.search(sentence) or is_json_shaped(sentence):
        return True
    if _FIRST_PERSON_CHECK_RE.search(sentence) or _SELF_LEAD_RE.match(sentence):
        return True
    cue = _SELF_CUE_RE.search(sentence) is not None
    if cue and (_positive(_NOTHING_NEEDS_CHECK_RE, sentence)
                or (next(_self_subjects(sentence), None) is not None and _positive(_NO_FURTHER_CHECK_RE, sentence))):
        return True
    # compliance with the request and word-count lines: decided before the dated-item guard, since "the 1633 spelling of the
    # supplied text" and "the 300-word limit" carry numbers that date nothing
    if len(sentence) <= 400 and (_WORD_COUNT_RE.match(sentence) or _COMPLIANCE_RE.match(sentence) or _quoted_words_fidelity(sentence)):
        return True
    if _DATED_ITEM_RE.search(sentence):
        return False
    if _SELF_SUBJECT_RE.search(sentence) or _SELF_ACCURACY_RE.search(sentence):
        if _positive(_SELF_ACCURACY_RE, sentence) or _positive(_SELF_PREDICATE_RE, sentence):
            return True
        if _INFRASTRUCTURE_RE.search(sentence) and _positive(_INFRASTRUCTURE_VERB_RE, sentence):
            return True
    if not cue:
        return False
    if _structural_self_report(sentence):
        return True
    subjects = [m.lastgroup for m in _self_subjects(sentence)]
    if subjects and _positive(_STRONG_MATCH_RE, sentence):
        return True
    return bool(_positive(_INFRA_AGENT_RE, sentence) and (_INFRA_OBJECT_RE.search(sentence) or any(k != "definite" for k in subjects)))


def is_word_count_line(sentence: str) -> bool:
    """Whether a sentence is only the answer's word count ("Word count: 52", "(52 words)", "Words: 52", "The word count is
    298."): a compliance self-report on a report's branches (role ``other``, advisory), and a measurement the channel
    makes itself, never a statement that anything was checked (repair round 5, ADV5-12)."""
    return len(sentence) <= 400 and _WORD_COUNT_RE.match(sentence.strip()) is not None


def is_self_certification(sentence: str) -> bool:
    """True when the sentence certifies the answer's own checking, on every branch the same way:

    * verification-status vocabulary (:data:`SELF_CERT_RE`) or the shape of a JSON receipt or payload;
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
      confirmed that every item is addressed", "The Overseer signed off on this answer").

    Only a POSITIVE predicate counts: a check under negation or a deontic modal ("The dates in this paragraph have not
    been checked", "... are from memory and should be checked before they are cited", "must be verified") is a
    disclaimer, never a self-certification. Answers are cached per sentence (pure function of the text)."""
    return _self_certification(sentence) if len(sentence) <= _CACHE_MAX_CHARS else _self_certification.__wrapped__(sentence)


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
#: A bare "from memory" closing a dated sentence ("... in February 1932 from memory.").
_TRAILING_BARE_LABEL_RE = re.compile(r"\s+(?:(?:quoted|given|cited|stated|recalled)\s+)?from (?:memory|recollection)(?=[.!?]?[\"'”’»)\]]*\s*$)", re.IGNORECASE)
#: How far before the sentence terminal :data:`_TRAILING_BARE_LABEL_RE` is looked for (the label is at most 30 characters).
_BARE_LABEL_WINDOW = 64
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
    text = text[: _terminal_start(text)]
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
    r"|sees?|saw|admits?|admitted|acknowledges?|acknowledged|emphasi[sz]es|emphasi[sz]ed|stresses|stressed|links?|linked|ties|tied")
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
#: ...", "Next step: trace find_position(scores, 12) yourself ...", "Confidence: lowered." (a self-rating of the answer).
#: Read with quotations masked, so a quoted "Note:" is the quoted text's. "Note that ..." (no colon) is an argument's own
#: signpost and stays substantive.
NOTE_LEAD_RE = re.compile(
    r"^[\s*_>#-]*(?:(?:please\s+)?note|notes|nb|next\s+steps?|confidence)\s*:"
    r"|^[\s*_>#-]*n\.\s?b\.(?:\s*:)?"
    r"|^[\s*_>#-]*note\s+on\b[^:.!?]{1,80}:",
    re.IGNORECASE,
)
_PAREN_SPAN_RE = re.compile(r"\s*\([^()]*\)")
_PAREN_INNER_RE = re.compile(r"\([^()]*\)")
_CLAUSE_SEPARATOR_RE = re.compile(r"[;—–]")
#: The shape of a sentence's terminal (stops, then closing marks and brackets, then spaces). Kept for callers; this module
#: finds it with :func:`_terminal_start`, a reverse scan, since searching for ``\s*$`` from every position of a long run of
#: spaces in the middle of a sentence is quadratic.
_TERMINAL_RE = re.compile(r"[.!?…]*[\"'”’»)\]]*\s*$")
_TERMINAL_STOPS = frozenset(".!?…")
_TERMINAL_CLOSERS = frozenset("\"'”’»)]")
#: A run of two or more whitespace characters: :func:`_split_note_clauses` reads a sentence with each run as one space.
_WHITESPACE_RUN_RE = re.compile(r"\s{2,}")
_LETTER_RE = re.compile(r"[^\W\d_]")


def _terminal_start(text: str) -> int:
    """Where the sentence terminal of ``text`` starts: the longest suffix made of sentence stops, then closing quotation
    marks and brackets, then whitespace (what :data:`_TERMINAL_RE` matches), found by one reverse scan."""
    i = len(text)
    while i > 0 and text[i - 1].isspace():
        i -= 1
    while i > 0 and text[i - 1] in _TERMINAL_CLOSERS:
        i -= 1
    while i > 0 and text[i - 1] in _TERMINAL_STOPS:
        i -= 1
    return i


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
    # Every run of whitespace is read as one space (the core's whitespace is tidied the same way at the end): a run of
    # tens of thousands of spaces in the middle of a sentence once made the terminal and label scans below quadratic.
    orig = _WHITESPACE_RUN_RE.sub(" ", sentence)
    masked = mask_quotations(orig)
    notes: list[str] = []
    # 0. a note lead ("Note:", "Note on ...:", "N.B.", "Next step:", "Confidence:") makes the whole sentence a note
    if NOTE_LEAD_RE.match(masked):
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
        body_end = _terminal_start(masked)  # the sentence's closing stop stays with the core
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
        body_end = _terminal_start(masked)
        comma = _PAREN_INNER_RE.sub(lambda m: "x" * len(m.group(0)), masked).rfind(",", 0, body_end)
        if comma < 0 or not masked[comma + 1:body_end].strip() or not _label_shaped(masked[comma + 1:body_end]):
            break
        notes.append(orig[comma + 1:body_end].strip())
        orig, masked = _cut(orig, masked, [(comma, body_end)])
    # the bare label closes the sentence, so only the sentence's last characters are read for it
    bare = _TRAILING_BARE_LABEL_RE.search(masked, max(0, _terminal_start(masked) - _BARE_LABEL_WINDOW))
    if bare is not None and _DATED_ITEM_RE.search(masked[:bare.start()]) and _LETTER_RE.search(masked[:bare.start()]):
        notes.append(orig[bare.start():bare.end()].strip())
        orig, masked = _cut(orig, masked, [(bare.start(), bare.end())])
    # 6. what remains is itself a label, a self-report, a task note or a note on how the answer was composed, or only
    #    filler around the labels removed: the whole sentence is a note
    if _LETTER_RE.search(masked) and (
        _label_shaped(masked) or is_self_certification(masked) or is_json_shaped(orig) or TASK_NOTE_RE.search(masked)
        or (notes and _filler_only(masked)) or is_provenance_note(orig.strip(" ,;:"))  # read on the words: a quoted label is a label
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


# ------------------------------------------------------------------ a conclusion drawn from the sentences before it

#: Subordinators that open a reason clause ("Since households borrowed less, ...", "Because the delegate objected to the
#: terms, ..."). "because of" is a cause phrase, not a clause; "as" and "for" are left out (their temporal and
#: prepositional readings are the common ones).
REASON_LEADS: tuple[tuple[str, ...], ...] = (("since",), ("because",), ("given", "that"), ("seeing", "that"), ("now", "that"))
#: A reason clause is read up to the comma that closes it, at most this many characters into the sentence.
_REASON_CLAUSE_MAX = 240
#: Doubled final consonants a stem keeps after "-ing" or "-ed" ("cutting" is "cutt"); folded on both sides of a comparison.
_DOUBLED_FINALS = frozenset("bdgmnprt")


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


# ------------------------------------------------------------------ a sentence that argues (repair round 3, ADV3-01)

#: Conclusion connectives: the clause after one is drawn from what stands before it ("A, so B", "So B.", "A; therefore B").
CONCLUSION_LEADS: tuple[tuple[str, ...], ...] = (
    ("so",), ("therefore",), ("thus",), ("hence",), ("consequently",), ("as", "a", "result"), ("it", "follows", "that"),
)
#: Evidential leads that open a conclusion drawn from the sentence before ("This shows that B.", "These figures suggest that B.").
_EVIDENTIAL_LEAD_RE = re.compile(
    r"^\W*(?:this|that|these|those|it|which)(?:\s+[a-z’'-]+){0,2}\s+(?:shows?|showed|suggests?|suggested|proves?|proved|demonstrates?|demonstrated"
    r"|indicates?|indicated|implies|implied|means|meant|confirms?|confirmed)\s+(?:that\s+)?\w", re.IGNORECASE)
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
        if inner.strip() and inner[0] != " " and len(inner.split()) >= min_words:
            spans.append((start, end + 1))
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
        return list(_quotation_spans.__wrapped__(text, min_single_words))
    return list(_quotation_spans(text, min_single_words))


#: The role a quoted span plays in the writer's sentence: ``quotation`` (words cited from a source: checked against the
#: supplied texts and attributed), ``correction`` (the right-hand side of a correction: "x" -> "y", "should be", "Model:"),
#: ``suggestion`` ("you could write ..."), ``mention`` (a word mentioned, not cited: a function word, or a span after a
#: negating frame such as 'without "like" or "as"'). Only a ``quotation`` is checked or attributed as a quotation; a span of
#: another role is the writer's own words, recorded with no source reference.
QUOTATION_ROLES: tuple[str, ...] = ("quotation", "correction", "suggestion", "mention")


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


def in_quotation_task(fn):
    """Decorator for a parser's ``parse_response``: its quotations are read in the task type it is given (its keyword
    ``task_type``, else the signature's default), unless an enclosing call (the channel) already set the task."""
    import inspect
    param = inspect.signature(fn).parameters.get("task_type")
    default = param.default if param is not None and param.default is not inspect.Parameter.empty else None

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with quotation_task(kwargs.get("task_type", default)):
            return fn(*args, **kwargs)
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
#: A label that opens the line (or a sentence of it) of a span and presents what follows as the writer's own corrected or
#: model text: it governs only a span that directly follows it ('Model: "Os recomiendo ..."', 'Two errors. Model: "..."'),
#: never the quotations inside the prose of a model paragraph ('Model: Her unease ... she "rehearsed three different first
#: sentences"' quotes the text and is checked).
_CORRECTION_LABEL_RE = re.compile(r"^[\s>*_#\d.)(-]*(?:model(?:\s+(?:answer|sentence|version|paragraph))?|corrected(?:\s+(?:version|sentence|form))?|correction|better"
                                  r"|improved(?:\s+version)?|rewrite|rewritten)\b[^:\"“”«»\n]{0,40}:[\s*_`]*$", re.IGNORECASE)
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
_SUGGESTION_LABEL_RE = re.compile(r"^[\s>*_#\d.)(-]*suggestions?\b[^:\"“”«»\n]{0,40}:[\s*_`]*$", re.IGNORECASE)
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


def _label_governs(prefix: str, pattern: "re.Pattern[str]") -> bool:
    """Whether a label of ``pattern`` opens the line, or a sentence of the line, right before the span (``prefix``: the
    line's text before the span). The role reader uses :meth:`_LineIndex.label_governs`, which answers the same in linear
    time over a text; this form reads one prefix."""
    if pattern.match(prefix):
        return True
    last = None
    for m in _SENTENCE_START_RE.finditer(prefix):
        last = m
    return last is not None and pattern.match(prefix[last.end():]) is not None


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


def quotation_role(text: str, start: int, end: int, *, feedback: Optional[bool] = None) -> str:
    """The role (:data:`QUOTATION_ROLES`) of the quoted span ``text[start:end]`` (marks included), read from the closed
    frames around it (:func:`_span_roles`) in the task :func:`quotation_task` set (or ``feedback`` when given). A span
    :func:`find_quotation_spans` does not find is a ``quotation`` (the conservative reading: it is checked). A span's role
    is read from it and the spans before it only, so the roles of all the text's spans give it."""
    spans = find_quotation_spans(text)
    for k, (a, b, _inner) in enumerate(spans):
        if a == start and b == end:
            return _span_roles(text, spans, feedback=feedback)[k]
    return "quotation"


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


def uncited_quotation_spans(text: str, *, min_single_words: int = 2, feedback: Optional[bool] = None) -> list[tuple[int, int, str, str]]:
    """``(start, end, inner, role)`` for every quoted span of ``text`` whose role is not ``quotation`` (a correction, a
    suggestion or a mention): the writer's own words, which no check of words against a source reads. A reader that also
    holds quotations recorded elsewhere (a parser's uncredited-quotation assumption) uses it to leave those out too."""
    spans = find_quotation_spans(text, min_single_words=min_single_words)
    if not spans:
        return []
    return [(a, b, inner, role) for (a, b, inner), role in zip(spans, _span_roles(text, spans, feedback=feedback)) if role != "quotation"]


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
