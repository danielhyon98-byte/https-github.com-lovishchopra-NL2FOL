"""Fallback parser for subjects without a dedicated adapter: one claim per sentence or per line of working, roles from
shared cues (the first sentence of a prose paragraph is its point; the result of a worked part is the part's answer;
dated or figured sentences are evidence; verdict cues are judgements).

Claim ids are unique per agent on a task: ``g{paragraph}.{unit}@{agent}`` (``g4.2@economics-specialist``). Every report the
hub parses on the generic branch used to be numbered ``g1.1``, ``g1.2`` ... whatever its sender, so two such reports on one
task (Economics with Business, Physics with Mathematics) held the same ids and no synthesis citing them could be accounted
for (INT-REQ-016, INT-LEDGER-014). The agent qualifier keeps the id stable for the ledger and for supersession (the same
agent re-numbers the same claims the same way) while no two agents share one. ``g{p}.`` still opens every id of
paragraph ``p``.

Segmentation. Markdown furniture and pasted JSON blocks are removed before segmentation; a JSON span glued to the prose is
cut out as one ``other`` sentence of its own, so the prose before and after it is parsed as prose and its strings are never
quotations. A paragraph is read line by line:

* a line that opens with ``=`` or ``≈`` continues the equation of the line before it (one claim per equation chain); a
  line that ends on a comma or a connective ("..., so") and a soft-wrapped prose line (the next line opens with a
  lower-case word, neither line is working) continue the line before them; every other line break ends a claim, so each
  line of working, each list item and each result is a claim of its own;
* part labels are structure, not claims: a line that is only a part label with or without its mark allocation
  ("(a) [2]", "(i) [2 marks]", "Part (a) — find — 3 marks", "3.") opens a part and proposes no claim, and a label leading a
  line ("(a) Percentage change = ...", "2. Lucía Ferrer ...", "3. a) F: ...") opens a part whose answer stands on that
  line; mark annotations ("[1]", "[1 spare]", "[2 marks]", "M1" or "A1" after two spaces, "(M1)") are removed from the
  claim text and a fragment that is nothing else is no claim (``original_response`` keeps all of them); a table's
  separator row is furniture and its header row a heading;
* a line splits into sentences at ``.``, ``?`` or ``!`` (a closing quotation mark may follow: '."', '.”', '.»') and at the
  ``}`` / ``]`` closing a pasted JSON fragment, before a capital, a digit, an opening mark or an opening bracket.

Roles. Note sentences are roled ``other`` and never material: from-memory labels, self-certification, task notes, a
sentence opened by a note lead (``markdown.NOTE_LEAD_RE``: "Note:", "Note on ...:", "N.B.", "Next step:", "Confidence:",
and on this branch "Limit:"), a question, a heading (a short line ending in a colon, "Measure: ..." when it states no
working, "Working for (b):", "Diagram 1: ...", a short title line such as "2024 (no tax)" over the lines it heads). A
paragraph opened by a bare note lead ("Note:", "N.B.", "Next step:", "Limit:") is a note as a whole. Only the
self-certifying or receipt-shaped sentence itself is demoted, the rest of its paragraph keeps its roles, unless the
paragraph is nothing but notes or JSON (then every sentence is a note); every demotion for a self-report is named in an
unresolved issue. A line of working (an equation, an arithmetic expression, a relation, an arrow chain) or a bare value
("(-1, 3)") is never a note for having no letters: it is ``quantitative`` and supporting unless it is an answer.

A substantive sentence that carries an inline label ("(figures from memory; check your notes)", a sentence-initial "From
memory,", a comma-bounded ", from memory", a trailing ", a figure I give from memory" or ", though this date is from
memory") keeps its role with the label recorded once as an assumption; labels are read outside quotations, and only a
sentence whose core is empty is a note, so a label word inside a substantive sentence ("... is illustrative of how ...")
changes nothing. A disclaimer ("should be checked", "have not been verified") is a note, never a self-report; the
self-certifications every branch recognises (``markdown.is_self_certification``) carry the advisory status, and a note on
how the answer was composed or on what a received report says of its own figures is a note.

Materiality follows the answer, not the layout:

* in a prose paragraph (one logical line, or lines that are all plain sentences) the first sentence that is not a note,
  an "Assumption:" line or a judgement is the ``point`` (material), supported by the later sentences of the paragraph
  that are neither notes, judgements, consequences ("Therefore ...", "So ...", "Consumers therefore pay ..."), caveats
  ("However ...", "Although ...", "The limit of this argument ..."), answers nor assumptions; a judgement or consequence
  rests on the point and the claims before it, never on a later one; two labelled answers that open a paragraph
  ("Binary search: at most 10 passes. Linear search: at most 1,000 comparisons.") are coordinate points, neither
  supporting the other;
* a line-structured block (working, label-led lines, list items, table rows) has no point of its own;
* in a part, a line led by "Answer:", "Result:", "Results:", "Total:" or "Final answer:" is the part's answer; failing
  that, the last line of the part's first run of working is the answer, together with the lines before it that give the
  same quantity for another case ("t = 0 h: ... ", ..., "t = 24 h: ..."); a closing answer is a material ``point``
  supported by the part's earlier claims. Failing both, the part's opening claim (the answer on the label's line, or the
  first claim after a label-only line) is the material answer, supported by the claims after it; when the part carries a
  justification ("Why: ..."), every sentence of the opening line is an answer ("2. Lucía Ferrer, una maestra jubilada. En
  2020 reunió a doce vecinos ..."). A bare value opening a part ("(-1, 3)") is always an answer.

Supports never form a cycle: a point opening its paragraph or part rests only on plain later claims, a closing answer,
judgement or consequence only on earlier ones, and no answer supports another.

Quotations are found in double marks of any kind (straight, curly, guillemet, mixed, two adjacent marks as one nested
mark) and in single marks around two or more words, paired by context so a quotation that carries an apostrophe ('I don't
know') is still one quotation; a span the dangling mark of an unbalanced sentence leaves undelimited is recorded, not
attributed. A quotation is attributed by the rule every parser shares
(:func:`~epinoic_logic.adapters.sources.attribute_excerpt`): the supplied text that holds the words (in any recognised
form) wins, the one the sentence names when several do; one held by no text is credited to the one text the sentence
names (author, surname, title, a peer specialist by name, "the source text"), whether or not it holds the words; otherwise
when the sentence names several texts, to the one that governs the quotation in the sentence
(``sources.governing_document``: its possessive, the reporting clause's speaker, the text named nearest before it);
otherwise it is credited to no text and recorded as the assumption ``quotation with no supplied text to check it against:
"..."``, which the core pack reports as unverifiable (``CORE-SRC-003``). Working is read with quotations masked, so a
colleague's equation quoted by the writer is the colleague's evidence, not the writer's working.

A text is never credited for being supplied first. Claim texts respect the contract limit, and sentences beyond the
report's claim limit are merged into one ``other`` claim with an unresolved issue rather than crashing or vanishing.
``original_response`` is always verbatim."""
from __future__ import annotations

import itertools
import bisect
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from ..adapters.base import AdapterError
from ..adapters.english_specialist.parser import documents_named
from ..adapters.markdown import (
    NOTE_LEAD_RE, cited_quotation_spans, concludes_from_earlier, in_quotation_task, dangling_quote_offset, find_quotation_spans, is_note_sentence, is_self_certification, mask_quotations,
    opens_with_conclusion, split_json_spans, states_own_reason,
    split_note_clauses, strip_markup, truncate_claim_text,
)
from ..adapters.sources import attribute_excerpt, strip_trailing_punctuation
from ..ir.schema import SourceRef
from ..translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text

#: A sentence ends at ``.``, ``?`` or ``!`` (a closing quotation mark may follow: '."', '.”', '.»', ".’") or at the ``}`` /
#: ``]`` closing a pasted JSON fragment, before a capital, a digit, an opening mark or an opening bracket.
_SENT_RE = re.compile(r"(?:(?<=[.?!\]}])|(?<=[.?!][\"”»’]))\s+(?=[A-Z0-9\"'(“‘«„{\[])")
_NUM_RE = re.compile(r"\d")
_LETTER_RE = re.compile(r"[^\W\d_]")
_MIN_QUOTE_CHARS = 4
_JUDGE = ("therefore", "overall", "to a large extent", "on balance", "in conclusion", "recommend", "should", "outweigh")
#: A check the answer hands its reader: a sentence opened by a purpose clause or a lead that sets up a check ("To check your
#: method, binary_search(scores, 41) should print (8, 4).", "As a check, the frequencies should add up to 1000.", "If your
#: working is right, ..."). Its "should" is the result the check expects, not a judgement (repair round 4,
#: E2E-CS-FALSE-BARE-ASSERTION); the other judgement cues keep their reading.
_CHECK_TIP_RE = re.compile(
    r"^\W*(?:to\s+(?:check|verify|test|confirm)\b|as\s+an?\s+(?:quick\s+|final\s+|further\s+)?(?:check|test)\b"
    r"|(?:you\s+(?:can|could|may|might)\s+)?(?:check|verify|test)\s+(?:this|that|it|your|the\s+(?:answer|result|working|method|code|trace))\b"
    r"|if\s+(?:your|the)\s+(?:[\w-]+\s+){0,2}(?:is|are)\s+(?:right|correct)\b)", re.IGNORECASE)
_MAX_CLAIMS = 512
_TAIL_CLAIM_ID = "g.tail"
_SELF_REPORT = "self-certified in the response text"
_AGENT_TAG_MAX = 48

# ------------------------------------------------------------------ part labels and mark annotations

_ROMAN = r"(?:i{1,3}|iv|vi{0,3}|ix|x)"
#: A part label: "(a)", "a)", "(iii)", "iv)", "(2)", "2.", "2)", "3. a)", "3. (b)".
_LABEL_TOKEN = rf"(?:\(\s*(?:[a-h]|{_ROMAN}|\d{{1,2}})\s*\)|(?:[a-h]|{_ROMAN})\)|\d{{1,2}}[.)](?:\s*(?:\(\s*[a-h]\s*\)|[a-h]\)))?)"
_PART_LEAD_RE = re.compile(rf"^\s*(?:(?:part|question|q)\s*)?(?P<label>{_LABEL_TOKEN})(?=\s|$)", re.IGNORECASE)
#: A mark allocation: "[2]", "[1 spare]", "[2 marks]", "(3 marks)".
_MARK_ALLOC = r"(?:\[\s*\d{1,2}(?:\s*(?:marks?|spare))?\s*\]|\(\s*\d{1,2}\s*marks?\s*\))"
#: What may follow a part label on a label-only line: a command term between dashes and a mark allocation ("— find — 3 marks").
_LABEL_ONLY_REST_RE = re.compile(rf"\s*(?:[—–:-]\s*)?(?:[A-Za-z][A-Za-z ]{{0,30}}?\s*[—–-]\s*)?(?:{_MARK_ALLOC}|\d{{1,2}}\s*marks?)?\s*[:.]?\s*", re.IGNORECASE)
#: Markscheme codes: "M1", "A1", "R1", "N2", "AG", bare after two spaces or a tab, or in brackets.
_MARK_CODE = r"(?:[MARN]\d{1,2}|AG)"
_TRAILING_ANNOTATION_RE = re.compile(rf"(?:\s*{_MARK_ALLOC}|(?:\s{{2,}}|\t)\(?{_MARK_CODE}\)?|\s*\({_MARK_CODE}\))+(?=[.;,]?\s*$)")
_ANNOTATION_ONLY_RE = re.compile(rf"\s*(?:(?:{_MARK_ALLOC}|\(?{_MARK_CODE}\)?)\s*)+[.;,]?\s*")
_BULLET_RE = re.compile(r"^\s*[-*•–—]\s+")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")

# ------------------------------------------------------------------ line leads

_RESULT_LEAD_RE = re.compile(r"^\W*(?:results?|answers?|final\s+answers?|total)\s*:", re.IGNORECASE)
_WHY_LEAD_RE = re.compile(r"^\W*(?:why|reasons?|reasoning|because|justification)\s*:", re.IGNORECASE)
_ASSUMPTION_LEAD_RE = re.compile(r"^\W*assum(?:ption|ptions|ed|ing)\s*:", re.IGNORECASE)
#: Note leads of this branch besides the shared ones: "Limit:" (what the answer could not draw on).
_BRANCH_NOTE_LEAD_RE = re.compile(r"^\W*limits?\s*:", re.IGNORECASE)
#: A paragraph opened by a bare note lead is a note as a whole ("Note on ...:" introduces a discussion and is not).
_BARE_NOTE_LEAD_RE = re.compile(r"^[\s*_>#-]*(?:(?:(?:please\s+)?note|notes|nb|next\s+steps?|limits?)\s*:|n\.\s?b\.)", re.IGNORECASE)
_DIAGRAM_LINE_RE = re.compile(r"^\W*(?:axes|axis|curves?|change|shifts?|equilibri(?:um|a)|areas?|labels?|key|arrows?)\s*:", re.IGNORECASE)
_DIAGRAM_TITLE_RE = re.compile(r"^\W*(?:diagram|figure|graph|table)\s+\d{1,2}\s*[:.—–-]", re.IGNORECASE)
_MEASURE_LEAD_RE = re.compile(r"^\W*(?:measure|working(?:\s+for\b[^:]{0,30})?)\s*:", re.IGNORECASE)
#: A short label opening a sentence ("Binary search: ...", "Linear search: ...").
_LABEL_LEAD_RE = re.compile(r"^\W*[A-Z][\w’'-]*(?:\s+[\w’'()-]+){0,2}\s*:\s+\S")
_CONSEQUENCE_RE = re.compile(
    r"^\W*(?:therefore|thus|hence|so|consequently|accordingly|as\s+a\s+result|this\s+means|it\s+follows)\b(?!\s+(?:far|much|many|long|too)\b)"
    r"|^\W*(?:[\w’'-]+\s+){1,4}(?:therefore|thus|hence|consequently)\b",
    re.IGNORECASE,
)
_CAVEAT_RE = re.compile(
    r"^\W*(?:however|but|yet|although|though|nevertheless|nonetheless|admittedly|that\s+said|even\s+so|on\s+the\s+other\s+hand"
    r"|in\s+contrast|by\s+contrast|the\s+limit(?:ation)?s?\s+of)\b",
    re.IGNORECASE,
)
#: A relation or an arithmetic expression: the shape of a line of working.
_RELATION_RE = re.compile(r"(?<![=<>!])(?:=|≈|≠|≤|≥|⇒|→|<=|>=)(?!=)|\s[<>]\s")
_ARITHMETIC_RE = re.compile(r"\d\s*[×÷*^]\s*[\d($]|\d\s+[+−-]\s+[\d$(]|\d\s*/\s*\d")
_COPULA_RE = re.compile(r"\b(?:is|are|was|were|be|been|has|have|had|gives?|equals?|means?|falls?|rises?|shows?)\b", re.IGNORECASE)
_TERMINAL_PUNCT_RE = re.compile(r"[.!?…][\"'”’»)\]]*\s*$")
_QUESTION_RE = re.compile(r"\?[\"'”’»)\]]*\s*$")
_CONTINUATION_RE = re.compile(r"^\s*\$?\s*[=≈]")
_CONNECTIVE_END_RE = re.compile(r"(?:,|\b(?:so|and|or|but|then|because|since|that|which|where|whereas|hence|thus|therefore|giving))\s*$", re.IGNORECASE)
_SOFT_WRAP_NEXT_RE = re.compile(r"^\s*[a-z][a-z]")


def agent_claim_tag(agent_id: str) -> str:
    """The qualifier that makes this parser's claim ids unique per agent on a task: the agent id itself when it is short
    and plain (letters, digits, ``.``, ``_``, ``-``), else a cut of it with a digest, so two agents never share a tag."""
    tag = agent_id.strip()
    if tag and len(tag) <= _AGENT_TAG_MAX and re.fullmatch(r"[A-Za-z0-9._-]+", tag):
        return tag
    plain = re.sub(r"[^A-Za-z0-9._-]+", "-", tag).strip("-")[:40] or "agent"
    return f"{plain}-{sha256_text(agent_id)[:8]}"


def _is_working(masked: str) -> bool:
    return bool(_RELATION_RE.search(masked) or _ARITHMETIC_RE.search(masked))


def _strip_annotations(text: str) -> str:
    """``_TRAILING_ANNOTATION_RE.sub("", text).rstrip()``, decided in one linear pass. The pattern searched from every start
    is quadratic on a long run of white space inside a sentence (8 s for 20,000 spaces; parser-safety-3). Its matches all
    end at ``q``, the one place after which only ``[.;,]?\\s*`` remains and before which an annotation can close (an
    annotation never ends in white space or punctuation), so at most one span is removed: from the leftmost start whose
    rest up to ``q`` is a run of annotations. ``ok[p]`` says whether ``text[p:q]`` is such a run, computed once from the
    right. An annotation's own white space reaches the end of its run because its body opens with a bracket or a capital,
    so a start only reads the body after that run, which is read once per body start. White space and digits are those of
    the pattern (``str.isspace``, ``str.isdecimal``)."""
    start, q = _trailing_annotation_span(text)
    return (text if start is None else text[:start] + text[q:]).rstrip()


def _trailing_annotation_span(text: str) -> tuple[Optional[int], int]:
    """The span ``_TRAILING_ANNOTATION_RE`` removes from ``text``: ``(start, q)``, ``start`` None when it removes nothing."""
    n = len(text)
    w = n
    while w > 0 and text[w - 1].isspace():
        w -= 1
    q = w - 1 if w > 0 and text[w - 1] in ".;," else w
    if q <= 0:
        return None, q
    last = text[q - 1]
    if last not in "])G" and not last.isdecimal():
        # every annotation ends in a closing bracket, a digit or the G of "AG", and the last one ends at q: none can end
        # here (the common sentence ending in a word), so nothing is built (repair round 5, ADV5-13)
        return None, q
    ws_run = [0] * (q + 1)                # white space from p, inside text[:q]
    for p in range(q - 1, -1, -1):
        if text[p].isspace():
            ws_run[p] = ws_run[p + 1] + 1

    def skip_ws(i: int) -> int:
        return i + ws_run[i] if i < q else i

    def digits_end(i: int) -> Optional[int]:
        """The end of a run of one or two digits at ``i`` that no third digit follows (``\\d{1,2}`` then a non-digit)."""
        j = i
        while j < q and j - i < 3 and text[j].isdecimal():
            j += 1
        return j if 1 <= j - i <= 2 and not (j < n and text[j].isdecimal()) else None

    def word_end(i: int, words: tuple[str, ...]) -> Optional[int]:
        for word in words:
            if text.startswith(word, i) and i + len(word) <= q:
                return i + len(word)
        return None

    def alloc_end(b: int) -> Optional[int]:
        """``\\[\\s*\\d{1,2}(?:\\s*(?:marks?|spare))?\\s*\\]`` or ``\\(\\s*\\d{1,2}\\s*marks?\\s*\\)`` at ``b``."""
        opening = text[b]
        if opening not in "[(":
            return None
        j = digits_end(skip_ws(b + 1))
        if j is None:
            return None
        k = skip_ws(j)
        if opening == "[":
            if k < q and text[k] == "]":
                return k + 1
            m = word_end(k, ("marks", "mark", "spare"))
            close = "]"
        else:
            m = word_end(k, ("marks", "mark"))
            close = ")"
        if m is None:
            return None
        m = skip_ws(m)
        return m + 1 if m < q and text[m] == close else None

    def code_end(i: int) -> Optional[int]:
        """``[MARN]\\d{1,2}|AG`` at ``i``."""
        if text.startswith("AG", i) and i + 2 <= q:
            return i + 2
        if i < q and text[i] in "MARN":
            return digits_end(i + 1)
        return None

    def bracketed_code_end(b: int) -> Optional[int]:
        """``\\(`` code ``\\)`` at ``b``."""
        if text[b] != "(":
            return None
        e = code_end(b + 1)
        return e + 1 if e is not None and e < q and text[e] == ")" else None

    def bare_code_end(b: int) -> Optional[int]:
        """``\\(?`` code ``\\)?`` at ``b``: a closing bracket right after the code is part of it (nothing else can follow)."""
        e = code_end(b + 1 if text[b] == "(" else b)
        if e is None:
            return None
        return e + 1 if e < q and text[e] == ")" else e

    ok = [False] * (q + 1)
    ok[q] = True
    bodies: dict[int, tuple[bool, bool]] = {}
    start: Optional[int] = None
    for p in range(q - 1, -1, -1):
        lead = ws_run[p]
        b = p + lead
        if b >= q:
            continue
        if b not in bodies:
            any_lead = any(e is not None and e <= q and ok[e] for e in (alloc_end(b), bracketed_code_end(b)))
            spaced = bare_code_end(b)
            bodies[b] = (any_lead, spaced is not None and spaced <= q and ok[spaced])
        any_lead, spaced_ok = bodies[b]
        if any_lead or (spaced_ok and (lead >= 2 or (lead == 1 and text[p] == "\t"))):
            ok[p] = True
            start = p
    return start, q


#: An accuracy mark ("A1", "(A1)") closing a line of working: the markscheme credits that line's result. The pattern is the
#: definition; :func:`accuracy_marked` reads it in linear time, and is what the parsers call.
_ACCURACY_MARK_RE = re.compile(r"(?:(?:\s{2,}|\t)\(?A\d{1,2}\)?|\s*\(A\d{1,2}\))(?:\s*(?:\(?[MARN]\d{1,2}\)?|AG))*[.;,]?\s*$")


def _mark_digits_end(line: str, p: int) -> list[int]:
    """The ends of one or two decimal digits (``\\d{1,2}``) at ``p``."""
    n = len(line)
    if p >= n or not line[p].isdecimal():
        return []
    return [p + 1, p + 2] if p + 1 < n and line[p + 1].isdecimal() else [p + 1]


def accuracy_marked(line: str) -> bool:
    """``_ACCURACY_MARK_RE.search(line) is not None``, decided in one linear pass. The pattern searched from every start is
    quadratic on a long run of white space or of marks that never reaches the end of the line (seconds for 20,000
    characters; parser-safety-1 remainder). Here ``rest[p]`` says whether ``line[p:]`` is a run of marks (``(?:\\s*(?:\\(?
    [MARN]\\d{1,2}\\)?|AG))*``) then ``[.;,]?\\s*`` to the end, computed once from the right; a start then only needs the
    lead (white space and an ``A1`` or ``(A1)`` mark), whose white space must reach the end of its run because a mark
    follows it. White space and digits are those of the pattern (``str.isspace``, ``str.isdecimal``)."""
    n = len(line)
    w = len(line.rstrip())
    end = w - 1 if w > 0 and line[w - 1] in ".;," else w
    if end <= 0 or (line[end - 1] not in ")G" and not line[end - 1].isdecimal()):
        # the marks run to the end of the line, and each ends in a digit, a closing bracket or the G of "AG": a line that
        # ends otherwise holds none (repair round 5, ADV5-13: most lines end in a word)
        return False
    ws_run = [0] * (n + 1)          # length of the white-space run starting at p
    tail_ws = [False] * (n + 1)     # line[p:] is white space only
    tail_ws[n] = True
    for p in range(n - 1, -1, -1):
        if line[p].isspace():
            ws_run[p] = ws_run[p + 1] + 1
            tail_ws[p] = tail_ws[p + 1]
    rest = [False] * (n + 1)
    for p in range(n, -1, -1):
        if tail_ws[p] or (p < n and line[p] in ".;," and tail_ws[p + 1]):
            rest[p] = True
            continue
        q = p + ws_run[p]                                  # the marks' own white space, then a mark
        if q >= n:
            continue
        ends: list[int] = []
        if line.startswith("AG", q):
            ends.append(q + 2)
        r = q + 1 if line[q] == "(" else q
        if r < n and line[r] in "MARN":
            for e in _mark_digits_end(line, r + 1):
                ends.append(e)
                if e < n and line[e] == ")":
                    ends.append(e + 1)
        rest[p] = any(rest[e] for e in ends if e > p)
    for i in range(n):
        run = ws_run[i]
        if run >= 2 or (run == 1 and line[i] == "\t"):      # (?:\s{2,}|\t)\(?A\d{1,2}\)?
            s = i + run
            r = s + 1 if s < n and line[s] == "(" else s
            if r < n and line[r] == "A":
                for e in _mark_digits_end(line, r + 1):
                    if rest[e] or (e < n and line[e] == ")" and rest[e + 1]):
                        return True
        s = i + run                                          # \s*\(A\d{1,2}\)
        if s + 1 < n and line[s] == "(" and line[s + 1] == "A":
            for e in _mark_digits_end(line, s + 2):
                if e < n and line[e] == ")" and rest[e + 1]:
                    return True
    return False


def _logical_lines(paragraph: str) -> list[tuple[str, bool, bool]]:
    """``(line, is_table_header, accuracy_marked)`` for each logical line of ``paragraph``: continuation lines joined to the
    line before them (each physical line's mark annotations removed first), table separator rows dropped."""
    raw = paragraph.split("\n")
    out: list[list] = []
    for line in raw:
        if not line.strip():
            continue
        accuracy = accuracy_marked(line)
        line = _strip_annotations(line) if not _ANNOTATION_ONLY_RE.fullmatch(line) else line
        if _TABLE_SEPARATOR_RE.match(line) and "-" in line:
            if out and _TABLE_ROW_RE.match(out[-1][0]):
                out[-1][1] = True  # the row above a separator is the table's header
            continue
        if out and not _PART_LEAD_RE.match(line) and not _BULLET_RE.match(line) and not _TABLE_ROW_RE.match(line):
            prev = out[-1][0]
            prev_masked, line_masked = mask_quotations(prev), mask_quotations(line)
            joins = bool(_CONTINUATION_RE.match(line))
            if not joins and _CONNECTIVE_END_RE.search(_strip_annotations(prev)) and not _TABLE_ROW_RE.match(prev):
                joins = True
            if (not joins and _SOFT_WRAP_NEXT_RE.match(line) and not _TERMINAL_PUNCT_RE.search(prev.rstrip(":;"))
                    and not prev.rstrip().endswith((":", ";")) and not _is_working(prev_masked) and not _is_working(line_masked)):
                joins = True
            if joins:
                out[-1][0] = prev.rstrip() + "\n" + line.rstrip()
                out[-1][2] = out[-1][2] or accuracy
                continue
        out.append([line.rstrip(), False, accuracy])
    return [(line, header, accuracy) for line, header, accuracy in out]


def split_sentences(paragraph: str) -> list[str]:
    """Claim texts of ``paragraph`` as the parser segments it: one per sentence, line of working or list item; a pasted JSON
    span glued to the prose kept as one sentence of its own; part labels and mark annotations left out."""
    return [u.text for u in _units_of(paragraph, 0, _State())]


@dataclass
class _Unit:
    text: str
    para: int
    line: int                 # logical line number across the answer
    part: int                 # 0 outside any part
    lead: str = ""            # result | why | assumption | note | bare_note | heading | question | diagram | label | ''
    working: bool = False
    value: bool = False       # digits and no letters: a bare value ("(-1, 3)")
    is_json: bool = False
    opening: bool = False     # on the opening line of its part (the label's own line, or the first line after a label-only line)
    accuracy: bool = False    # closes a line that carried an accuracy mark ("A1"): a result the markscheme credits


#: Lines that never open a part's answer: diagram description, headings, notes and questions.
_NOT_OPENING = frozenset({"diagram", "heading", "note", "bare_note", "question"})


@dataclass
class _State:
    line: int = 0
    part: int = 0
    awaiting_opening: bool = False   # a label-only line opened the current part; its opening line is still to come


def _line_heading(body: str, has_following: bool) -> bool:
    """A heading line: a short line closing on a colon ("Working for (b):"), or a short title over the lines it heads
    ("2024 (no tax)", "2025"). Sentence-level headings ("Measure: ..." stating no working, "Diagram 1: ...") are read by
    :func:`_classify` on the sentence that carries them."""
    masked = mask_quotations(body).strip()
    words = masked.split()
    if masked.endswith(":") and len(words) <= 8 and not _is_working(masked):
        return True
    return (has_following and len(words) <= 4 and not _TERMINAL_PUNCT_RE.search(masked) and not _is_working(masked)
            and not _COPULA_RE.search(masked) and not find_quotation_spans(body))


def _units_of(paragraph: str, para_index: int, state: _State) -> list[_Unit]:
    units: list[_Unit] = []
    lines = _logical_lines(paragraph)
    for li, (line, header, accuracy) in enumerate(lines):
        state.line += 1
        m = _PART_LEAD_RE.match(line)
        if m is not None:
            state.part += 1
            rest = line[m.end():]
            if _LABEL_ONLY_REST_RE.fullmatch(rest):
                state.awaiting_opening = True
                continue  # a label-only line opens a part and proposes no claim
            body, opening = rest, True
            state.awaiting_opening = False
        else:
            body, opening = _BULLET_RE.sub("", line, count=1), False
        body = _strip_annotations(body)
        if not body.strip() or _ANNOTATION_ONLY_RE.fullmatch(body):
            continue
        heading = header or (m is None and _line_heading(body, li < len(lines) - 1))
        line_units: list[_Unit] = []
        for piece, is_json in split_json_spans(body.strip()):
            sents = [piece] if is_json else [s.strip() for s in _SENT_RE.split(piece) if s.strip()]
            for s in sents:
                s = s if is_json else _strip_annotations(s)
                if not s or (not is_json and _ANNOTATION_ONLY_RE.fullmatch(s)):
                    continue
                line_units.append(_classify(_Unit(text=s, para=para_index, line=state.line, part=state.part, is_json=is_json), heading))
        if not line_units:
            continue
        if state.awaiting_opening and not heading and m is None and not all(u.lead in _NOT_OPENING for u in line_units):
            opening, state.awaiting_opening = True, False
        for u in line_units:
            u.opening = opening
        line_units[-1].accuracy = accuracy  # the result an accuracy mark credits closes its line
        units.extend(line_units)
    return units


def _classify(u: _Unit, heading: bool) -> _Unit:
    masked = mask_quotations(u.text)
    u.working = not u.is_json and _is_working(masked)
    u.value = not u.is_json and bool(_NUM_RE.search(u.text)) and not _LETTER_RE.search(u.text)
    if u.is_json:
        u.lead = ""
    elif _BARE_NOTE_LEAD_RE.match(masked) or _BRANCH_NOTE_LEAD_RE.match(masked):
        u.lead = "bare_note"
    elif NOTE_LEAD_RE.match(masked):
        u.lead = "note"
    elif heading or (masked.rstrip().endswith(":") and len(masked.split()) <= 4 and not u.working) or _DIAGRAM_TITLE_RE.match(masked) \
            or (_MEASURE_LEAD_RE.match(masked) and not u.working):
        u.lead = "heading"  # "Measure: ..." stating no working, "Working for (b):", "Diagram 1: ...", "Ask yourself:"
    elif _QUESTION_RE.search(masked):
        u.lead = "question"
    elif _RESULT_LEAD_RE.match(masked):
        u.lead = "result"
    elif _WHY_LEAD_RE.match(masked):
        u.lead = "why"
    elif _ASSUMPTION_LEAD_RE.match(masked):
        u.lead = "assumption"
    elif _DIAGRAM_LINE_RE.match(masked):
        u.lead = "diagram"
    elif _LABEL_LEAD_RE.match(masked):
        u.lead = "label"
    return u


def _mask_quotations(sentence: str) -> str:
    """``sentence`` with its quoted spans blanked, so a name inside a quotation never names a source."""
    out = list(sentence)
    for start, end, _inner in find_quotation_spans(sentence):
        out[start:end] = " " * (end - start)
    return "".join(out)


def quotations_in(sentence: str) -> list[str]:
    """The quoted excerpts of ``sentence``: double marks of any kind (paired around the
    dangling mark of an unbalanced sentence, two adjacent marks as one nested mark) and
    single marks around two or more words; the strings of a pasted JSON span are not quotations."""
    return [inner for _s, _e, inner in cited_quotation_spans(sentence) if len(inner.strip()) >= _MIN_QUOTE_CHARS]


def _lead_shape(text: str) -> str:
    """A line of working with its figures masked ("t = 0 h: 1620 − 20 = 1600 ± 32 counts min⁻¹" -> "t = # h: # − # = # ± #
    counts min⁻¹"): two lines with one shape give one quantity for two cases. A formula and its substitution differ."""
    masked = " ".join(mask_quotations(text).split()).lower()
    return re.sub(r"\d+(?:[.,]\d+)*", "#", masked) if "#" not in masked and _NUM_RE.search(masked) else ""


def _parallel_rows(units: list[_Unit], answer: int, candidates: list[int]) -> list[int]:
    """The lines of working just before ``answer`` in its paragraph that give the same quantity for another case."""
    shape = _lead_shape(units[answer].text)
    if not shape:
        return []
    rows: list[int] = []
    for k in reversed([c for c in candidates if c < answer]):
        prev = units[k]
        if prev.para != units[answer].para or not prev.working or _lead_shape(prev.text) != shape or prev.line == units[answer].line:
            break
        rows.append(k)
        answer = k
    return rows


@dataclass
class RoleAssignment:
    """Roles of the units of an answer (:func:`assign_roles`): per unit (in document order) its role, whether it is
    material, a consequence, a caveat or a part's answer; the supports (unit index -> the indices it rests on); and the
    unresolved issues to report (verification-status language demoted)."""
    roles: list[str]
    material: list[bool]
    supports: dict[int, list[int]]
    consequence: list[bool]
    caveat: list[bool]
    answer: list[bool]
    unresolved: list[str]


#: How many sentences before it a reason clause or a ground phrase may restate (repair round 5, rerun-parser-safety-11 variant:
#: every sentence of a paragraph was read against every sentence before it, quadratic in a long list).
_EARLIER_REACH = 64


def assign_roles(para_units: list[list[_Unit]], quoted: list[bool]) -> RoleAssignment:
    """The roles, materiality and supports of segmented units (see the module docstring), by paragraph: notes, then the
    cue roles (a consequence or a judgement cue: judgement; a quotation, ``quoted[i]``: evidence; a figure:
    quantitative; analysis otherwise), the paragraph's point, each part's answer and the conclusions that rest on the
    claims before them. Shared by every parser that segments as this one does (the STEM branches' parser builds its
    units from its own statements)."""
    flat: list[_Unit] = [u for units in para_units for u in units]
    n = len(flat)
    roles: list[str] = ["other"] * n
    material: list[bool] = [False] * n
    supports: dict[int, list[int]] = {}
    consequence: list[bool] = [False] * n
    caveat: list[bool] = [False] * n
    answer: list[bool] = [False] * n
    unresolved: list[str] = []
    index = 0
    para_ranges: list[tuple[int, int]] = []
    for pi, units in enumerate(para_units):
        start = index
        index += len(units)
        para_ranges.append((start, index))
        if not units:
            continue
        sents = [u.text for u in units]
        cores = [split_note_clauses(s)[0] for s in sents]
        reports = [k for k, s in enumerate(sents) if is_self_certification(s)]
        notes_flags = [GenericTextParser._is_note(units[k], cores[k], k in reports) for k in range(len(units))]
        note_paragraph = all(notes_flags) or units[0].lead == "bare_note"
        demoted = [f"sentence {k + 1} ('{sents[k][:80]}')" for k in reports]
        if demoted and not note_paragraph:
            unresolved.append(f"paragraph {pi + 1}: {len(demoted)} sentence(s) carrying verification-status language were roled other and count as no material claim; "
                              f"the other sentences of the paragraph keep their roles: {'; '.join(demoted)[:600]}")
        elif demoted and len(sents) > 1:
            unresolved.append(f"paragraph {pi + 1} is nothing but notes and verification-status language; the whole paragraph was treated as a note and none of its sentences counts as material")
        earlier_texts: list[str] = []  # the paragraph's sentences so far that are no notes, grown as it is read (one pass)
        for k, u in enumerate(units):
            i = start + k
            sent = u.text
            core = cores[k]
            if note_paragraph or notes_flags[k]:
                roles[i] = "other"
                continue
            prior = earlier_texts[-_EARLIER_REACH:]
            earlier_texts.append(core or sent)
            low = (core or sent).lower()
            opening_command = u.opening and (k == 0 or units[k - 1].line != u.line)  # "(b) Hence, ...": the question's command term
            # a consequence cue ('Therefore ...', 'So ...'), or a reason clause that restates a claim before it ('Household borrowing
            # fell ... . Since households borrowed less, the rate rise reduced spending.'): the sentence concludes from what came
            # before, so it rests on it (repair round 2, NAME-LINK-NONDISCRIMINATING: the text delivery reads it as a report does)
            # an evidential lead after the paragraph's first sentence ('This shows that ...', 'These figures suggest that ...') draws its
            # conclusion from what came before in the same way (repair round 3, ADV3-01)
            consequence[i] = not opening_command and (bool(_CONSEQUENCE_RE.match(mask_quotations(core or sent))) or (
                k > 0 and (concludes_from_earlier(core or sent, prior) or opens_with_conclusion(core or sent))))
            caveat[i] = bool(_CAVEAT_RE.match(mask_quotations(core or sent)))
            cues = [kw for kw in _JUDGE if kw in low]
            if cues == ["should"] and _CHECK_TIP_RE.match(mask_quotations(core or sent)):
                cues = []  # the result a check expects (_CHECK_TIP_RE)
            if consequence[i] or (cues and not opening_command):
                roles[i] = "judgement"
            elif quoted[i]:
                roles[i] = "evidence"
            elif _NUM_RE.search(core or sent):
                roles[i] = "quantitative"
            else:
                roles[i] = "analysis"
        GenericTextParser._paragraph_points(units, start, roles, material, supports, consequence, caveat)
    GenericTextParser._part_answers(flat, roles, material, supports, answer, consequence, caveat)
    GenericTextParser._backward_conclusions(flat, para_ranges, roles, supports, answer, consequence)
    return RoleAssignment(roles, material, supports, consequence, caveat, answer, unresolved)


class GenericTextParser:
    def __init__(self, agent_id: str = "specialist") -> None:
        self.agent_id = agent_id

    @in_quotation_task
    def parse_response(self, text: str, *, request_id: str, task_id: str, report_id: str, subject: str, task_type: str, supplied_texts: list[SuppliedText] = (),
                       course_level: str = "unknown", agent_version: Optional[str] = None, agent_id: Optional[str] = None) -> SpecialistReport:
        if not text or not text.strip():
            raise AdapterError("the specialist answer is empty")
        agent = agent_id or self.agent_id
        tag = agent_claim_tag(agent)
        base = dict(request_id=request_id, task_id=task_id, report_id=report_id, agent_id=agent, agent_version=agent_version, subject=subject, course_level=course_level, task_type=task_type)
        unresolved: list[str] = []
        docs = {t.document_id: t for t in supplied_texts}
        paragraphs = [p.strip("\n") for p in re.split(r"\n\s*\n", strip_markup(text).strip()) if p.strip()]
        state = _State()
        para_units: list[list[_Unit]] = [_units_of(para, pi, state) for pi, para in enumerate(paragraphs)]
        flat: list[_Unit] = [u for units in para_units for u in units]
        if not flat:
            raise AdapterError("the specialist answer yields no sentences")

        n = len(flat)
        refs_of: list[list[SourceRef]] = [[] for _ in range(n)]
        assumptions_of: list[list[str]] = [[] for _ in range(n)]
        quoted: list[bool] = [False] * n
        for i, u in enumerate(flat):
            sent = u.text
            excerpts = quotations_in(sent) if not u.is_json else []
            named = documents_named(_mask_quotations(sent), docs) if (docs and excerpts) else []
            for ex in excerpts:
                doc, notes_for_excerpt = attribute_excerpt(ex, named, docs, sentence=sent)
                if doc:
                    # punctuation written inside the closing mark is the writer's, as the English parser reads it (repair round 2)
                    refs_of[i].append(SourceRef(document_id=doc, excerpt=(strip_trailing_punctuation(ex) or ex)[:2000]))
                assumptions_of[i].extend(notes_for_excerpt)
            if not u.is_json and dangling_quote_offset(sent) is not None:
                assumptions_of[i].append("the sentence has an unbalanced quotation mark; the span it opens or closes was not treated as a quotation and was not checked")
            core, notes = split_note_clauses(sent)
            if core:  # a substantive sentence keeps its role; the inline label travels as an assumption (each distinct label once)
                for note in notes:
                    assumptions_of[i].append(f"inline label recorded, not part of the claim: {note[:200]}")
            quoted[i] = bool(refs_of[i] or excerpts)
        assigned = assign_roles(para_units, quoted)
        unresolved.extend(assigned.unresolved)
        roles, material, supports = assigned.roles, assigned.material, assigned.supports

        pending: list[dict] = []
        counters: dict[int, int] = {}
        for i, u in enumerate(flat):
            counters[u.para] = counters.get(u.para, 0) + 1
            cid = f"g{u.para + 1}.{counters[u.para]}@{tag}"
            role = roles[i]
            mat = material[i] or role in ("point", "judgement")
            kind = "arithmetic" if role == "quantitative" else ("factual" if role == "evidence" and not refs_of[i] else "unknown")
            pending.append(dict(claim_id=cid, claim_text=truncate_claim_text(u.text), claim_role=role, proposed_claim_kind=kind,
                                source_refs=refs_of[i], assumptions=assumptions_of[i][:32], materiality="material" if mat and role != "other" else "supporting",
                                advisory_verification_status=_SELF_REPORT if is_self_certification(u.text) else None))
        ids = [p["claim_id"] for p in pending]
        support_ids = {ids[i]: [ids[s] for s in sorted(set(ss)) if s != i] for i, ss in supports.items() if roles[i] != "other"}
        tail_id = _TAIL_CLAIM_ID  # the fold claim of an oversized answer keeps its fixed id (pinned by the History regressions)
        if len(pending) > _MAX_CLAIMS:
            head, tail = pending[: _MAX_CLAIMS - 1], pending[_MAX_CLAIMS - 1:]
            head.append(dict(claim_id=tail_id, claim_text=truncate_claim_text(" ".join(p["claim_text"] for p in tail)), claim_role="other", proposed_claim_kind="unknown", source_refs=[], assumptions=[], materiality="supporting", advisory_verification_status=None))
            unresolved.append(f"{len(tail)} sentences beyond the report's claim limit ({_MAX_CLAIMS}) were merged into claim {tail_id} and were not individually roled or checked")
            pending = head
        kept = {p["claim_id"] for p in pending}
        claims = [ClaimRecord(**base, **{**p, "supporting_claim_ids": [s for s in support_ids.get(p["claim_id"], []) if s in kept][:_MAX_CLAIMS]}) for p in pending]
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return SpecialistReport(report_id=report_id, request_id=request_id, task_id=task_id, agent_id=agent, agent_version=agent_version, subject=subject, course_level=course_level,
                                task_type=task_type, original_response=text, response_sha256=sha256_text(text), supplied_texts=list(supplied_texts), claims=claims,
                                unresolved_issues=unresolved[:64], created_at=now)

    # -------------------------------------------------------------- roles

    @staticmethod
    def _is_note(u: _Unit, core: str, self_report: bool) -> bool:
        """A note: a self-report, a note lead, a heading, a question, or a sentence whose core is empty once its labels are
        set aside. A line of working or a bare value is never a note for having no letters."""
        if self_report or u.lead in ("note", "bare_note", "heading", "question"):
            return True
        if u.is_json:
            return not core or is_note_sentence(core)
        if (u.working or u.value) and _NUM_RE.search(u.text):
            return bool(core) and is_note_sentence(core) and _LETTER_RE.search(core) is not None
        return not core or is_note_sentence(core)

    @staticmethod
    def _paragraph_points(units: list[_Unit], start: int, roles: list[str], material: list[bool], supports: dict[int, list[int]],
                          consequence: list[bool], caveat: list[bool]) -> None:
        """The point of a prose paragraph: its first claim that is not a note, an assumption or a judgement, supported by the
        plain claims after it. Two labelled answers opening the paragraph are coordinate points. A line-structured block
        (working, label-led lines, list items, table rows) has no point of its own."""
        live = [start + k for k, u in enumerate(units) if roles[start + k] != "other"]
        if len(live) == 1 and roles[live[0]] != "point":
            # a paragraph whose one claim argues, stating its own reason ("The town opened a library in 2015, and pollution fell
            # in 2016, so the library caused the fall"), is its own point: material, as the History and English parsers read it
            # (repair round 4, ADV4-10: it stayed 'supporting', so a warning named on it reached the receipt as no INT-ARG-001)
            only = units[live[0] - start]
            if not only.working and states_own_reason(split_note_clauses(only.text)[0] or only.text) is not None:
                material[live[0]] = True
        if len(units) < 2 or not live:
            return
        lines = {u.line for u in units}
        structured = len(lines) > 1 and any(u.working or u.lead or u.value for u in units)
        if structured:
            return
        leads = {start + k: u.lead for k, u in enumerate(units)}
        labelled = [i for i in live[:2] if leads[i] == "label"]
        if len(labelled) == 2:
            for i in live:
                if leads[i] != "label":
                    break
                roles[i], material[i] = "point", True
            return
        first = live[0]
        if leads[first] in ("assumption", "diagram"):
            return
        later = [i for i in live[1:] if roles[i] not in ("judgement",) and not consequence[i] and not caveat[i] and leads[i] not in ("assumption",)]
        if roles[first] == "judgement":
            # a judgement that opens its paragraph ('The email should receive 10 out of 12. The rubric awards ... . The email has
            # only ...') is the paragraph's point: the plain sentences after it are its reasons, as on the English branch
            # (repair round 2, MISS-UNCH-RUBRIC-TEXT); a consequence ('So ...') opening a paragraph still rests on nothing later
            if not consequence[first] and later:
                material[first] = True
                supports[first] = later
            return
        roles[first], material[first] = "point", True
        supports[first] = later

    @staticmethod
    def _part_answers(flat: list[_Unit], roles: list[str], material: list[bool], supports: dict[int, list[int]], answer: list[bool],
                      consequence: list[bool], caveat: list[bool]) -> None:
        """Each part's answer is material (see the module docstring): a result-led line, else the last line of the part's
        first run of working (with its parallel rows), else the part's opening claim; a bare value opening a part always."""
        parts: dict[int, list[int]] = {}
        for i, u in enumerate(flat):
            if u.part:
                parts.setdefault(u.part, []).append(i)
        leads = [u.lead for u in flat]
        # the units of each line and the lines of each paragraph, read once for every part (repair round 5, rerun-parser-safety-11
        # variant: each part rebuilt both over every unit of the answer, O(parts × units) at the response bound)
        lines_of: dict[int, list[int]] = {}
        para_lines: dict[int, set[int]] = {}
        for i, u in enumerate(flat):
            lines_of.setdefault(u.line, []).append(i)
            para_lines.setdefault(u.para, set()).add(u.line)
        # the claims each claim supports, so a closing answer leaves the support lists that hold it without a scan of every list
        # (an entry may go stale when a list is replaced; it is checked before use)
        holders: dict[int, set[int]] = {}
        for p, ss in supports.items():
            for s_ in ss:
                holders.setdefault(s_, set()).add(p)

        def drop_support(i: int) -> None:
            for p in holders.pop(i, ()):
                ss = supports.get(p)
                if ss and i in ss:
                    supports[p] = [s_ for s_ in ss if s_ != i]

        def set_supports(i: int, ss: list[int]) -> None:
            supports[i] = ss
            for s_ in ss:
                holders.setdefault(s_, set()).add(i)

        for _part, members in parts.items():
            live = [i for i in members if roles[i] != "other"]
            if not live:
                continue
            closing: list[int] = []
            results = [i for i in live if leads[i] == "result" or flat[i].accuracy]
            if results:
                # the sentence that carries the lead is the answer; the sentences after it on its line keep their roles
                closing = results
            else:
                run = GenericTextParser._first_working_run(flat, live, lines_of, para_lines)
                if run:
                    last = run[-1]
                    closing = [*reversed(_parallel_rows(flat, last, run)), last]
            opening = [i for i in live if flat[i].opening and leads[i] not in ("diagram", "assumption")]
            opening_answers: list[int] = []
            if opening and not closing:
                first_line = flat[opening[0]].line
                on_line = [i for i in opening if flat[i].line == first_line]
                justified = any(leads[i] == "why" for i in live)
                if not flat[on_line[0]].text.rstrip().endswith(":"):
                    if justified:  # "2. Lucía Ferrer, una maestra jubilada. En 2020 reunió ...\nWhy: ...": every sentence of the line answers
                        opening_answers = on_line
                    elif len(on_line) > 1 and all(leads[i] == "label" for i in on_line[:2]):  # "Binary search: ... Linear search: ..."
                        opening_answers = list(itertools.takewhile(lambda i: leads[i] == "label", on_line))
                    else:
                        opening_answers = on_line[:1]
            elif opening and flat[opening[0]].value:
                opening_answers = [opening[0]]
            for i in closing + opening_answers:
                answer[i] = True
                material[i] = True
            # the claims a closing answer may rest on, in order, once per part (no answer, no diagram, no note): each closing
            # answer reads those before it (repair round 5, rerun-parser-safety-11 variant: every closing answer scanned the
            # whole part, quadratic in a part of parallel rows)
            eligible = [j for j in live if not answer[j] and leads[j] != "diagram" and roles[j] != "other"] if closing else []
            for i in closing:
                # a closing answer rests on the claims before it in its paragraph and on the part's earlier lines of working and
                # the quotations they use, not on every remark the part made before it
                earlier = [j for j in eligible[:bisect.bisect_left(eligible, i)]
                           if flat[j].para == flat[i].para or flat[j].working or roles[j] == "evidence"]
                # a closing answer rests on what came before it; it is no other claim's support
                drop_support(i)
                if roles[i] == "point" and i in supports:
                    supports.pop(i)
                if earlier:
                    roles[i] = "point"
                    set_supports(i, earlier)
            for i in opening_answers:
                if i in closing:
                    continue
                para = flat[i].para
                # a bare answer alone in its paragraph ("(-1, 3)"): what follows in the part justifies it, and the first
                # sentence of that justification is not a point of its own
                alone = not any(j > i and flat[j].para == para for j in live)
                pool = [j for j in live if j > i and (alone or flat[j].para == para)]
                later = [j for j in pool if not answer[j] and roles[j] != "judgement" and (alone or roles[j] != "point") and not consequence[j]
                         and not caveat[j] and leads[j] not in ("assumption", "diagram")]
                drop_support(i)
                roles[i] = "point" if later or roles[i] in ("point", "analysis") else roles[i]
                set_supports(i, later)
                for j in later:
                    if roles[j] == "point":
                        roles[j], material[j] = ("quantitative" if _NUM_RE.search(flat[j].text) else "analysis"), False
                        supports.pop(j, None)

    @staticmethod
    def _first_working_run(flat: list[_Unit], live: list[int], lines_of: Optional[dict[int, list[int]]] = None,
                           para_lines: Optional[dict[int, set[int]]] = None) -> list[int]:
        """The part's first run of working: the working claims of the consecutive paragraphs, from the first that holds a line
        of working, that each hold one. A line of working stands on a line of its own or in a line-structured block; an
        equation inside a sentence of a prose paragraph is the prose's, and a diagram line is description, not working.
        ``lines_of`` (the units of each line) and ``para_lines`` (the lines of each paragraph) are the answer's, read once
        by the caller; they are built here when not given."""
        by_para: dict[int, list[int]] = {}
        for i in live:
            by_para.setdefault(flat[i].para, []).append(i)
        if lines_of is None or para_lines is None:
            lines_of, para_lines = {}, {}
            for i, u in enumerate(flat):
                lines_of.setdefault(u.line, []).append(i)
                para_lines.setdefault(u.para, set()).add(u.line)
        structured = {p for p in by_para if len(para_lines.get(p, ())) > 1}
        run: list[int] = []
        started = False
        for para in sorted(by_para):
            working = [i for i in by_para[para] if flat[i].working and flat[i].lead not in ("diagram", "heading")
                       and (para in structured or len(lines_of[flat[i].line]) == 1)]
            if working:
                started = True
                run.extend(working)
            elif started:
                break
        return run

    @staticmethod
    def _backward_conclusions(flat: list[_Unit], para_ranges: list[tuple[int, int]], roles: list[str], supports: dict[int, list[int]],
                              answer: list[bool], consequence: list[bool]) -> None:
        """A judgement or consequence rests on its paragraph's point and the claims before it, never on a later one."""
        for start, end in para_ranges:
            for i in range(start, end):
                if (roles[i] != "judgement" and not consequence[i]) or answer[i]:
                    continue
                # a point never rests on a judgement or a consequence, so the edge from an earlier claim cannot close a cycle
                earlier = [j for j in range(start, i) if roles[j] != "other"]
                if earlier:
                    supports[i] = earlier
