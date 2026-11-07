"""Which ES-META-001 findings are an agent's self-report (rule ``meta-note``, round-8 clearance c1).

The English pack names every meta-text paragraph of an answer ES-META-001 (warning), and the delivery policy's rule
``self-report-disclosed`` refuses the FORMALLY CHECKED label to an answer whose receipt carries an agent's self-report at
any severity. ES-META-001 names two kinds of meta-text: a SELF-REPORT (a self-certification, a narrated check, a pasted
receipt, a verification label) and a NOTE (a provenance note, "Note: I can't see the image, so the visual points rest on
the image descriptions in your pasted text.", or a study suggestion, "Next step: write your own paragraph on the same two
strands and paste it here for feedback."). The knowledge bases ask every answer to close with such a line, so in round c1
all four English answers carried ES-META-001 for a note and none could ever be delivered FORMALLY CHECKED.

This module reads the journaled answer again, deterministically, and frees an ES-META-001 from the rule only when the
paragraph it names is positively read as a note:

* only a PARAGRAPH-level ES-META-001 can name a note (its message opens ``paragraph N is meta-text (``, written by the pack's
  own code); a sentence-level one names a sentence that narrates a check, certifies the answer or imitates a receipt, which
  is always a self-report;
* the answer is segmented by the English parser itself (:func:`~epinoic_logic.adapters.english_specialist.parser.segment`,
  the reading the pack used), and paragraph N must be meta-text there;
* the paragraph opens with a bare note lead as the parsers read it (``Note:``, ``Notes:``, ``NB``, ``N.B.``, ``Next
  step(s):``, ``Limit(s):``, ``Caveat(s):``; :func:`~epinoic_logic.adapters.markdown.opens_note_paragraph`), and nothing in
  it reads as a self-report: no JSON, no sentence a shared reader names (the English parser's meta sentence, the core
  pack's self-certification vocabulary and verification labels, the auditor's own structural detector), and no
  ASSURANCE WORD (rule ``assurance-words``, read with quotations masked): a closed vocabulary of checking, verification,
  accuracy, agreement, approval and system words ("checked", "verified", "accurate", "exact", "matches", "fine", "spot
  on", "word for word", "as written", "line up", "approved", "passed", "QA", "engine", "word count", a check mark, "no
  errors", a first-person check "I check ...", "I looked at ...", "I made sure ..."), a fault denied ("none of the
  quotations is wrong", "no quotation was altered": a denial of a fault certifies), except a negative form of an
  assurance word ("unchecked", "unverified", "imprecise" is no assurance at all) in a clause that holds no other negator
  ("the dates are the History specialist's and unchecked here" is a note; "no figure is unchecked" certifies). A
  base-form checking verb that opens a study suggestion and takes an object ("Next step: check your quotations against
  the extract") is the suggestion's verb, not a check done;
* and the paragraph has the positive FORM of a note (rule ``note-form``; an allowlist, never a blocklist alone): a ``Next
  step(s):`` paragraph is a study suggestion, so one of its clauses opens with a verb of a suggestion addressed to the
  student ("write", "rewrite", "plan", "paste", "take", "try", ...); any other lead is a limitation or provenance note, so
  it states a limitation ("can't", "not", "only", "unchecked", "practice", "fictional", "from memory", "rest on", ...). A
  meta paragraph that has neither ("Note: each quote matches the source.", "Note: I looked at each quotation again and
  they are fine.") is no note, whatever vocabulary it avoids.

Anything else is a self-report, and so is anything the rule cannot read (a segmentation failure, a paragraph number that
names no meta-text paragraph): the rule never frees what it cannot read, so it can only ever move an answer from the
fallback to the formal path when the meta-text is a note; a note it misreads as a self-report keeps the answer out of the
formal path, as before the rule. Every reader here is linear in the text (one token scan, each clause's negators counted
once; the segmentation is the pack's own). Like every check, it proves a property of the text and this code only.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

__all__ = ["META_NOTE_RULE", "ASSURANCE_RULE", "NOTE_FORM_RULE", "note_paragraphs", "is_note_paragraph", "assurance_words", "note_form",
           "meta_paragraph_of", "self_report_findings"]

META_NOTE_RULE = "meta-note"
ASSURANCE_RULE = "assurance-words"
NOTE_FORM_RULE = "note-form"

#: The paragraph-level message of ES-META-001, written by the English pack's own code (``structural.meta_findings``).
_META_PARAGRAPH_RE = re.compile(r"paragraph (\d{1,6}) is meta-text \(")
#: One token: a word (apostrophes and hyphens inside it), a number, a check mark, or one clause boundary.
_TOKEN_RE = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*|\d+|[✓✔☑✅]|[,;:.!?()\[\]—–]")
_BOUNDARY = frozenset(",;:.!?()[]—–")
#: Participles and adjectives of checking, verification, accuracy and approval: an assurance in the affirmative.
_ASSURANCE_WORDS = frozenset({
    "checked", "rechecked", "re-checked", "cross-checked", "crosschecked", "double-checked", "doublechecked", "triple-checked",
    "fact-checked", "factchecked", "spot-checked", "verified", "reverified", "confirmed", "validated", "certified", "approved", "audited",
    "reviewed", "tested", "proven", "proved", "guaranteed", "signed", "passed", "passes", "accurate", "accurately", "accuracy", "exact",
    "exactly", "correct", "correctly", "correctness", "reliable", "reliably", "reliability", "trustworthy", "faithful", "faithfully",
    "flawless", "flawlessly", "precise", "precisely", "authentic", "genuine", "rigorous", "rigorously", "error-free", "verbatim",
    "airtight", "watertight", "infallible", "definitive", "qa", "z", "engine", "solver", "overseer", "receipt", "receipts", "word-count",
    # third-person present of a checking act: "the engine confirms each claim", "this ensures every figure ..."
    "checks", "verifies", "confirms", "validates", "certifies", "proves", "guarantees", "ensures", "assures",
    # agreement and approval in plain words (round-8 clearance c1): "each quote matches the source", "they are fine"
    "match", "matches", "matched", "matching", "identical", "identically", "fine", "right", "okay", "ok", "perfect", "perfectly", "compared",
    "proofread", "proof-read", "tallied", "traced", "cross-referenced", "faultless", "watertight", "spotless", "impeccable",
    "✓", "✔", "☑", "✅",
})
#: Adjectives and verbs of a fault: denied anywhere in their clause ("none of the quotations is wrong", "no quotation was
#: altered", "I did not change any figure") they certify the answer. (A fault NOUN certifies only right after "no", "zero",
#: "without" or "free of": "no errors"; "does not address the issue of cost" is a limitation.)
_FAULT_WORDS = frozenset({"wrong", "incorrect", "inaccurate", "mistaken", "false", "misquoted", "misquote", "misquotes", "invented", "invent",
                          "altered", "alter", "changed", "change", "fabricated", "fabricate", "distorted", "made-up", "garbled", "erroneous",
                          "misread", "misreported", "miscounted", "miscalculated"})
#: Phrases of assurance (token sequences): "word for word", "as written", "spot on", "line(s) up", "made sure", "all good".
_ASSURANCE_PHRASES = (("word", "for", "word"), ("as", "written"), ("spot", "on"), ("line", "up"), ("lines", "up"), ("lined", "up"),
                      ("made", "sure"), ("make", "sure"), ("all", "good"), ("looks", "good"), ("all", "fine"), ("all", "clear"), ("word", "count"),
                      ("double", "checked"), ("went", "through"), ("gone", "through"), ("read", "through"), ("looked", "at"), ("looked", "over"),
                      ("letter", "for", "letter"), ("to", "the", "letter"), ("in", "full", "agreement"))
#: Past forms of a checking act after a first-person subject: "I looked at each quotation", "we read every line again".
_FIRST_PERSON_PAST = frozenset({"looked", "went", "read", "reread", "re-read", "compared", "counted", "matched", "made", "ensured", "tested",
                                "traced", "scanned", "reviewed", "proofread", "examined", "inspected", "confirmed", "checked", "verified"})
#: Rule ``note-form``: the verbs that open a study suggestion addressed to the student ("Next step: write your own paragraph").
_SUGGESTION_VERBS = frozenset({
    "write", "rewrite", "re-write", "plan", "paste", "send", "take", "try", "practise", "practice", "read", "reread", "re-read", "revise", "add",
    "use", "find", "choose", "draft", "redraft", "underline", "highlight", "learn", "start", "keep", "focus", "aim", "ask", "consider",
    "think", "swap", "replace", "expand", "cut", "link", "explain", "analyse", "analyze", "answer", "attempt", "time", "spend", "turn", "set",
    "look", "list", "compare", "check", "apply", "build", "sketch", "outline", "select", "pick", "record", "redo", "work", "bring", "identify",
    "annotate", "memorise", "memorize", "prepare", "structure", "finish", "repeat", "label", "quote", "embed", "cite", "share", "upload",
    "return", "compose", "create", "test", "revisit", "review", "go", "move", "do", "give", "tell", "show", "complete", "submit", "copy",
})
#: Rule ``note-form``: the words of a limitation or provenance note ("I can't see the image", "unchecked here", "fictional
#: practice data", "from memory", "rest on the image descriptions").
_LIMITATION_WORDS = frozenset({
    "can't", "cannot", "couldn't", "unable", "not", "no", "never", "without", "none", "isn't", "aren't", "wasn't", "weren't", "don't", "doesn't",
    "didn't", "haven't", "hasn't", "unchecked", "unverified", "unverifiable", "unseen", "unknown", "unclear", "uncertain", "only", "practice",
    "ungraded", "unofficial", "fictional", "fictitious", "hypothetical", "illustrative", "invented", "imaginary", "approximate", "approximately",
    "approx", "estimate", "estimated", "estimates", "rounded", "assume", "assumed", "assuming", "assumption", "assumptions", "memory", "recall",
    "recalled", "rest", "rests", "based", "depend", "depends", "depending", "if", "may", "might", "missing", "absent", "limited", "limitation",
    "limitations", "partial", "partly", "simplified", "omitted", "excerpt", "extract", "summary", "paraphrase", "paraphrased", "translated",
    "translation", "described", "descriptions", "description", "image", "images", "provisional", "draft", "unofficial",
})
#: Stems read as assurance whatever their ending ("verification", "certificate", "validation").
_ASSURANCE_STEMS = ("verif", "certif", "validat")
#: Base forms of a checking act: an assurance after a first-person subject ("I check every quotation"), the verb of a study
#: suggestion when it opens one and takes an object ("Next step: check your quotations").
_CHECK_VERBS = frozenset({"check", "recheck", "cross-check", "double-check", "verify", "confirm", "validate", "review", "test", "prove", "compare",
                          "proofread", "certify", "audit"})
_FIRST_PERSON = frozenset({"i", "we"})
#: What may stand between a first-person subject and its checking act: "I have now carefully checked", "we also verify".
_FIRST_PERSON_GAP = frozenset({"have", "has", "had", "do", "did", "also", "now", "then", "carefully", "fully", "personally", "already", "always", "each",
                               "all", "both", "just", "to"})
#: The object a suggestion's checking verb takes ("check your ...", "verify the ...", "compare each ...").
_OBJECT_OPENERS = frozenset({"your", "the", "each", "every", "a", "an", "this", "these", "that", "those", "it", "them", "one", "two", "all", "any",
                             "whether", "how", "what", "which", "against"})
#: Nouns of a fault: "no errors", "zero mistakes", "without issues" certify the answer.
_FAULT_NOUNS = frozenset({"error", "errors", "mistake", "mistakes", "issue", "issues", "problem", "problems", "fault", "faults", "flaw", "flaws",
                          "typo", "typos", "inaccuracy", "inaccuracies", "discrepancy", "discrepancies"})
#: Negators: a negative form of an assurance word beside one of them is affirmative again ("nothing here is unverified").
_NEGATORS = frozenset({"no", "not", "nothing", "none", "never", "nobody", "neither", "nor", "without", "zero", "cannot", "unable"})
#: Negative forms of assurance words: no assurance at all, unless a negator stands in their clause.
_NEGATIVE_FORMS = frozenset({"unchecked", "unverified", "unverifiable", "unconfirmed", "unvalidated", "uncertified", "unapproved", "unaudited",
                             "unreviewed", "untested", "unproven", "unproved", "unsigned", "unreliable", "untrustworthy", "unfaithful", "inaccurate",
                             "inaccurately", "incorrect", "incorrectly", "inexact", "imprecise", "inauthentic"})
_MAX_PARAGRAPH_CHARS = 20_000


def _tokens(text: str) -> list[str]:
    return [t.lower().replace("’", "'") for t in _TOKEN_RE.findall(text)]


def _negator(tok: str) -> bool:
    return tok in _NEGATORS or tok.endswith("n't")


def _clauses(toks: list[str]) -> list[list[str]]:
    out: list[list[str]] = [[]]
    for t in toks:
        if t in _BOUNDARY:
            if out[-1]:
                out.append([])
        else:
            out[-1].append(t)
    return [c for c in out if c]


def _first_person_before(clause: list[str], i: int) -> Optional[str]:
    """The first-person subject ("i", "we", "i've", "we've", "i'd") of the act at ``i``, across the gap words, else None."""
    j = i - 1
    while j >= 0 and clause[j] in _FIRST_PERSON_GAP:
        j -= 1
    if j >= 0 and (clause[j] in _FIRST_PERSON or clause[j] in ("i've", "we've", "i'd", "we'd", "i'm")):
        return clause[j]
    return None


def assurance_words(text: str) -> list[str]:
    """The assurance words of ``text`` (rule ``assurance-words``; quotations should be masked by the caller): every word of
    the closed vocabulary read in the affirmative, every phrase of assurance ("word for word", "as written", "spot on",
    "line up", "made sure"), every negative form ("unchecked") and every fault word ("wrong", "altered", "errors") whose
    clause holds a negator (a fault denied certifies), every first-person checking act ("I check ...", "I looked at ...").
    A checking verb in its base form that opens a clause and takes an object ("check your quotations against the
    extract", "correct the second paragraph") is an imperative, the verb of a suggestion, never a check done. One linear
    scan of the tokens: each clause's negators are counted once."""
    found: list[str] = []
    for clause in _clauses(_tokens(text)):
        n = len(clause)
        negators = sum(1 for t in clause if _negator(t))
        for i, t in enumerate(clause):
            nxt = clause[i + 1] if i + 1 < n else ""
            phrase = next((ph for ph in _ASSURANCE_PHRASES if tuple(clause[i:i + len(ph)]) == ph), None)
            if phrase is not None and not (i == 0 and phrase[0] in ("make", "read", "looked")):
                found.append(" ".join(phrase))  # "word for word", "spot on", "made sure" ("make sure your ..." opening a clause is a suggestion)
                continue
            if t in _NEGATIVE_FORMS:
                if negators:
                    found.append(t)  # "nothing here is unverified": a double negative certifies
                continue
            if t in _FAULT_WORDS:
                if negators:
                    found.append(f"denied {t}")  # "none of the quotations is wrong", "I did not alter any quotation"
                continue
            if t in _FAULT_NOUNS:
                prev = clause[i - 1] if i else ""
                before2 = clause[i - 2] if i >= 2 else ""
                if prev in ("no", "zero", "without") or (before2 in ("no", "zero", "without") and prev in ("further", "more", "other", "known")) \
                        or (prev == "of" and before2 == "free"):
                    found.append(f"{prev} {t}")  # "no errors", "without issues", "free of errors"
                continue
            if t in _FIRST_PERSON_PAST and _first_person_before(clause, i):
                found.append(f"{_first_person_before(clause, i)} {t}")  # "I looked at each quotation", "we read every line again"
                continue
            if t in _CHECK_VERBS or t == "correct":
                if i == 0 and nxt in _OBJECT_OPENERS:
                    continue  # an imperative opening a clause: "check your quotations", "correct the dates" (a suggestion)
                if t == "correct":
                    if not _negated_here(clause, i, negators):
                        found.append(t)  # "all figures are correct"
                    continue
                who = _first_person_before(clause, i)
                if who:
                    found.append(f"{who} {t}")  # "I check every quotation", "we also verify": a narrated check
                continue
            if t in _ASSURANCE_WORDS or t.startswith(_ASSURANCE_STEMS):
                if _negated_here(clause, i, negators):
                    continue  # "the dates have not been checked", "these cannot be verified": a disclaimer
                found.append(t)
    return found


def _negated_here(clause: list[str], i: int, negators: int) -> bool:
    """Whether the assurance word at ``i`` is negated by a negator within the four tokens before it, with no second negator
    in its clause (``negators`` counts them once per clause: a double negative certifies)."""
    if not any(_negator(t) for t in clause[max(0, i - 4):i]):
        return False
    return negators == 1


def note_form(text: str) -> bool:
    """Rule ``note-form``: whether the meta paragraph ``text`` (quotations masked by the caller) has the positive form of a
    note. After a ``Next step(s):`` lead, a clause opens with a verb of a suggestion addressed to the student (a study
    suggestion); after any other lead, a word of limitation or provenance stands in it (a limitation note). One linear scan."""
    toks = _tokens(text)
    if not toks:
        return False
    lead_next = len(toks) >= 2 and toks[0] == "next" and toks[1] in ("step", "steps")
    if lead_next:
        return any(_opens_suggestion(c) for c in _clauses(toks[2:]))
    return any(t in _LIMITATION_WORDS or t.endswith("n't") for t in toks)


#: Words that may stand before the verb of a suggestion in its clause: "so plan your second analysis", "then rewrite ...".
_SUGGESTION_LEADS = frozenset({"so", "and", "then", "now", "please", "first", "next", "also", "just", "but", "instead", "or", "today", "later"})


def _opens_suggestion(clause: list[str]) -> bool:
    """Whether ``clause`` opens with the verb of a suggestion, after at most two lead words ("so plan ...", "and then write")."""
    i = 0
    while i < len(clause) and i < 2 and clause[i] in _SUGGESTION_LEADS:
        i += 1
    return i < len(clause) and clause[i] in _SUGGESTION_VERBS


def is_note_paragraph(text: str) -> bool:
    """True when the meta-text paragraph ``text`` is positively read as a note (module docstring): a bare note lead, no
    JSON, no sentence a shared self-report reader names, no narration and no assurance word. Never raises: a text it cannot
    read is no note."""
    try:
        return _is_note_paragraph(text)
    except Exception:  # noqa: BLE001 - a reader that fails frees nothing (fail closed: a self-report)
        return False


def _is_note_paragraph(text: str) -> bool:
    from ..adapters.english_specialist.parser import META_NARRATION_RE, is_meta_sentence, split_sentences
    from ..adapters.markdown import find_json_spans, is_json_block, mask_quotations, opens_note_paragraph, self_cert_vocabulary
    from ..adapters.markdown import verification_label
    from .checks.selfcert import flags_self_certification
    if not text or len(text) > _MAX_PARAGRAPH_CHARS or not opens_note_paragraph(text):
        return False
    if is_json_block(text) or find_json_spans(text):
        return False
    masked = mask_quotations(text)
    if META_NARRATION_RE.search(masked):
        return False
    for s in split_sentences(text):
        if is_meta_sentence(s) or self_cert_vocabulary(s) is not None or verification_label(s) is not None or flags_self_certification(mask_quotations(s)):
            return False
    return not assurance_words(masked) and note_form(masked)


def note_paragraphs(text: str) -> frozenset[int]:
    """The 1-based indices of the English answer ``text``'s meta-text paragraphs that are notes (rule ``meta-note``), as
    the English parser segments it. Never raises: an answer it cannot segment has none."""
    try:
        from ..adapters.english_specialist.parser import segment
        return frozenset(p.index for p in segment(text or "") if p.kind == "meta" and is_note_paragraph(p.text))
    except Exception:  # noqa: BLE001 - fail closed: no paragraph is freed
        return frozenset()


def meta_paragraph_of(finding: Any) -> Optional[int]:
    """The paragraph number of a paragraph-level ES-META-001 (``paragraph N is meta-text (...)``), else None (a sentence-level
    one, another code, a message the pack did not write so)."""
    if getattr(finding, "code", None) != "ES-META-001":
        return None
    m = _META_PARAGRAPH_RE.match(str(getattr(finding, "message", "") or ""))
    return int(m.group(1)) if m is not None else None


def self_report_findings(findings: Iterable[Any], report: Any) -> list[Any]:
    """``findings`` (receipt findings of the self-report codes) without the ES-META-001 findings that name a note paragraph
    of the journaled ``report``'s answer (rule ``meta-note``). The answer is read only when such a finding is present."""
    found = list(findings)
    if not any(meta_paragraph_of(f) is not None for f in found):
        return found
    text = getattr(report, "original_response", None) if report is not None else None
    notes = note_paragraphs(text) if isinstance(text, str) else frozenset()
    return [f for f in found if not (meta_paragraph_of(f) in notes and not list(getattr(f, "claim_ids", []) or []))]
