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

A claim's agent-stated certainty is the writer's own hedge, read outside quotations (``markdown.hedged_certainty``):
``possible`` for "may have", "might have", "could have", "may be", "possibly", "perhaps"; ``probable`` for "probably",
"most likely", "presumably", "arguably", "appears to", "suggests"; ``established`` otherwise. A synthesis that states a
hedged claim as established is then named by the hub (INT-LEDGER-003).

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

import bisect
import heapq
import itertools
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from collections.abc import Sequence
from typing import Optional

from ..adapters.base import AdapterError
from ..adapters.english_specialist.parser import documents_named
from ..adapters.history_specialist.parser import is_source_caveat
from ..adapters.markdown import (
    BARE_NOTE_LEAD_RE,
    NOTE_LEAD_RE, dangling_quote_offset, find_quotation_spans, hedged_certainty, in_quotation_task, is_note_sentence, is_self_certification, mask_quotations,
    parser_quotation_spans,
    split_json_spans, split_note_clauses, strip_markup, truncate_claim_text,
)
from ..adapters.sources import attribute_excerpt
from ..ir.schema import SourceRef
from ..stem.layout import ANNOTATION_RUN_CONTINUATION_RE, JoinedLine, strip_trailing_annotations, trailing_annotation_span
from ..translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text

#: A sentence ends at ``.``, ``?`` or ``!`` (a closing quotation mark may follow: '."', '.”', '.»', ".’") or at the ``}`` /
#: ``]`` closing a pasted JSON fragment, before a capital, a digit, an opening mark or an opening bracket.
_SENT_RE = re.compile(r"(?:(?<=[.?!\]}])|(?<=[.?!][\"”»’]))\s+(?=[A-Z0-9\"'(“‘«„{\[])")
_NUM_RE = re.compile(r"\d")
_LETTER_RE = re.compile(r"[^\W\d_]")
_MIN_QUOTE_CHARS = 4
_JUDGE = ("therefore", "overall", "to a large extent", "on balance", "in conclusion", "recommend", "should", "outweigh")
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
#: Blank runs read possessively (rule linear-readers, integration gate 1; the same strings match): as written it was cubic in a
#: run of blanks after a part label (``stem.layout.LABEL_ONLY_REST_RE`` holds the same pattern).
_LABEL_ONLY_REST_RE = re.compile(rf"\s*+(?:[—–:-]\s*+)?(?:[A-Za-z][A-Za-z ]{{0,30}}?\s*+[—–-]\s*+)?(?:{_MARK_ALLOC}|\d{{1,2}}\s*+marks?)?\s*+[:.]?\s*+", re.IGNORECASE)
#: Markscheme codes: "M1", "A1", "R1", "N2", "AG", bare after two spaces or a tab, or in brackets.
_MARK_CODE = r"(?:[MARN]\d{1,2}|AG)"
_TRAILING_ANNOTATION_RE = re.compile(rf"(?:\s*{_MARK_ALLOC}|(?:\s{{2,}}|\t)\(?{_MARK_CODE}\)?|\s*\({_MARK_CODE}\))+(?=[.;,]?\s*$)")
_ANNOTATION_ONLY_RE = re.compile(rf"\s*(?:(?:{_MARK_ALLOC}|\(?{_MARK_CODE}\)?)\s*)+[.;,]?\s*")
#: :data:`_ANNOTATION_ONLY_RE` (the pattern the STEM layout shares) with possessive blank runs, which this parser reads whole lines with
#: (integration gate 2): the blanks after the last mark and the blanks after the optional stop were adjacent runs, split in every way
#: before a line with text after its marks failed, k² steps ('(A1)' + blanks + 'x': 0.2 s at 8,000 blanks). Every run is followed by a
#: mark, a stop or the line's end, so the lines matched are the same.
_ANNOTATION_ONLY_LINEAR_RE = re.compile(rf"\s*+(?:(?:{_MARK_ALLOC}|\(?{_MARK_CODE}\)?)\s*+)+[.;,]?\s*+")
_BULLET_RE = re.compile(r"^\s*[-*•–—]\s+")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*+\|?\s*+:?-{2,}+:?\s*+(?:\|\s*+:?-{2,}+:?\s*+)*+\|?\s*+$")  # linear (stem.layout)
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")

# ------------------------------------------------------------------ line leads

_RESULT_LEAD_RE = re.compile(r"^\W*(?:results?|answers?|final\s+answers?|total)\s*:", re.IGNORECASE)
_WHY_LEAD_RE = re.compile(r"^\W*(?:why|reasons?|reasoning|because|justification)\s*:", re.IGNORECASE)
_ASSUMPTION_LEAD_RE = re.compile(r"^\W*assum(?:ption|ptions|ed|ing)\s*:", re.IGNORECASE)
#: Note leads of this branch besides the shared ones: "Limit:" (what the answer could not draw on).
_BRANCH_NOTE_LEAD_RE = re.compile(r"^\W*limits?\s*:", re.IGNORECASE)
#: A paragraph opened by a bare note lead is a note as a whole ("Note on ...:" introduces a discussion and is not): the shared lead
#: (``markdown.BARE_NOTE_LEAD_RE``: "Note:", "N.B.", "Next step:", "Limit:", "Caveat:"), which the channel's word bound reads too.
_BARE_NOTE_LEAD_RE = BARE_NOTE_LEAD_RE
#: A caveat that its sources do NOT vouch for something ('do not confirm the exact 1990 rate', 'were unavailable'): a figure it names is
#: what is not confirmed, so the sentence is a note; a caveat that its sources confirm a figure states the figure and keeps its substance.
_NEGATIVE_CAVEAT_RE = re.compile(r"\b(?:do|does|did|could|can)\s*(?:not|n['’]t)\s+(?:confirm|verify|give|state|record|cover|support|include)\b|\bcannot\s+(?:confirm|verify)\b"
                                 r"|\b(?:unavailable|not\s+available|not\s+been\s+(?:checked|confirmed|verified|available))\b", re.IGNORECASE)
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
#: :data:`_CONSEQUENCE_RE` with the run of non-word characters before the words read possessively (integration gate 2): the run overlaps
#: the word class (a hyphen or an apostrophe is both), so a line of hyphens ('-' * k) was split between the run and the first word in
#: every way, n² steps (0.9 s at 10,000 characters). The possessive run gives every match of the pattern but one kind: a word of hyphens
#: or apostrophes alone that the pattern counts as the one word before the keyword ("’  Thus much"), which the run now takes; that kind is
#: read apart (:data:`_CONSEQUENCE_MARK_WORD_RE`), so :func:`_is_consequence` is the pattern's truth.
_CONSEQUENCE_LINEAR_RE = re.compile(
    r"^\W*+(?:therefore|thus|hence|so|consequently|accordingly|as\s+a\s+result|this\s+means|it\s+follows)\b(?!\s+(?:far|much|many|long|too)\b)"
    r"|^\W*+(?:[\w’'-]+\s+){1,4}(?:therefore|thus|hence|consequently)\b",
    re.IGNORECASE,
)
_CONSEQUENCE_LEAD_RE = re.compile(r"^(\W*+)(?:therefore|thus|hence|consequently)\b", re.IGNORECASE)
_CONSEQUENCE_MARK_WORD_RE = re.compile(r"[’'-]\s+\Z")


def _is_consequence(text: str) -> bool:
    """``bool(_CONSEQUENCE_RE.match(text))`` in linear time (:data:`_CONSEQUENCE_LINEAR_RE`)."""
    if _CONSEQUENCE_LINEAR_RE.match(text):
        return True
    lead = _CONSEQUENCE_LEAD_RE.match(text)
    return lead is not None and _CONSEQUENCE_MARK_WORD_RE.search(lead.group(1)) is not None
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
_CONTINUATION_RE = re.compile(r"^\s*+\$?\s*+[=≈]")  # blank runs possessive: linear, the same lines (stem.layout)
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
    """``_TRAILING_ANNOTATION_RE.sub("", text).rstrip()`` in linear time: the STEM layout's reader of the same pattern
    (``stem.layout.strip_trailing_annotations``; tests/stem/test_layout.py holds the two patterns identical). The pattern
    searched as written re-read a run of annotations from each of them, quadratic in the run (integration gate 1)."""
    return strip_trailing_annotations(text)


#: An accuracy mark ("A1", "(A1)") closing a line of working: the markscheme credits that line's result. A match starts only
#: where no whitespace precedes (``(?<!\s)``): a match starting inside a run of blanks ends where the run's own match ends (the
#: blanks before the mark are read greedily either way), so the matches are those of the pattern without the anchor, read in
#: linear time; unanchored, the search read the rest of a long run of blanks from each of them, n² steps (integration gate 1:
#: 3.2 s of a 4.0 s Physics crossing of 20,000 blanks, through the STEM parser's units).
_ACCURACY_MARK_RE = re.compile(r"(?<!\s)(?:(?:\s{2,}|\t)\(?A\d{1,2}\)?|\s*\(A\d{1,2}\))(?:\s*(?:\(?[MARN]\d{1,2}\)?|AG))*[.;,]?\s*$")
#: :data:`_ACCURACY_MARK_RE` read from the end of the line (the line reversed, the pattern reversed, matched once at the start): the
#: pattern ends at the end of the line, so it matches somewhere exactly when its reversal matches the reversed line from its start
#: (``(?<!\s)`` before the mark is ``(?!\s)`` after it). Searched forwards, every mark of a long run of marks ('(A1) (A1) ...')
#: started a match that read the rest of the run before failing at the line's last character, n² steps (integration gate 2: 0.6 s at
#: 10,000 characters through the generic and STEM parsers, hours at the size limit); reversed, the run is read once.
_ACCURACY_MARK_REVERSED_RE = re.compile(r"\s*[.;,]?(?:(?:\)?\d{1,2}[MARN]\(?|GA)\s*+)*(?:\)?\d{1,2}A\(?(?:\s{2,}|\t)|\)\d{1,2}A\(\s*)(?!\s)")


def _accuracy_marked(line: str) -> bool:
    """``bool(_ACCURACY_MARK_RE.search(line))`` in linear time (:data:`_ACCURACY_MARK_REVERSED_RE`)."""
    return "A" in line and _ACCURACY_MARK_REVERSED_RE.match(line[::-1]) is not None


#: A character that no mark annotation and no run of them holds (``stem.layout._ANNOTATION_RUN_RE``: blanks, brackets, digits, the
#: letters of "mark(s)", "spare" and of the markscheme codes): a trailing run of annotations starts after the last such character.
_ANNOTATION_BARRIER_RE = re.compile(r"[^\s\d\[\]()aekmprsAGMNR]")
#: What ends an annotation: a closing bracket, or a markscheme code ("M1", "AG").
_ANNOTATION_CLOSER_RE = re.compile(r"[\])]|[MARN]\d|AG")
#: Characters a working test can turn on (:data:`_RELATION_RE`'s signs; masking a quotation can only hide a match, or turn one on
#: at a sign by hiding the sign before it).
_RELATION_SIGN_RE = re.compile(r"[=≈≠≤≥⇒→<>]")
#: How many characters the join rules may read a whole logical line for, per character of the answer, and beyond that
#: (integration gate 2): see :class:`_LogicalLine`.
_JOIN_READ_PER_CHAR = 8
_JOIN_READ_FLOOR = 20_000


def _unmasked(line: str) -> str:
    return line


class _JoinBudget:
    """The characters the join rules of one answer (or of one paragraph read on its own) may still read a whole logical line for:
    :data:`_JOIN_READ_PER_CHAR` per character of the text, and :data:`_JOIN_READ_FLOOR` more."""

    __slots__ = ("left",)

    def __init__(self, chars: int) -> None:
        self.left = _JOIN_READ_PER_CHAR * chars + _JOIN_READ_FLOOR

    def pay(self, chars: int) -> bool:
        if chars > self.left:
            return False
        self.left -= chars
        return True


class _LogicalLine:
    """A logical line of :func:`_logical_lines`: its physical lines (each with its trailing blanks removed; none blank), and what
    the join rules ask of the joined text, kept as lines are added (integration gate 2). The rules asked their patterns of the
    whole joined text for every line it absorbed and copied it to add each line, n² steps on an answer of joined lines ('ab cd'
    on each of 8,000 lines: 35 s; the same 48 KB as one paragraph through an Economics hub, 30 s). Each answer is the
    pattern's on the joined text (tests/branches/test_integration_gate2_handoff.py holds them equal on random paragraphs):

    * the closing punctuation, the closing colon and the table row are read by :class:`~epinoic_logic.stem.layout.JoinedLine`;
    * the connective ending what is left once the trailing mark annotations are removed: when the last line holds a character no
      annotation holds (a closing stop aside), the trailing run of annotations lies in that line, so the line and the characters
      before it are read; otherwise the whole text is read;
    * the working test with quotations masked (``mask_quotations``, which pairs the marks of the whole text): it can turn on
      only at a relation sign or at arithmetic of the text unmasked (:class:`~epinoic_logic.stem.layout.WorkingReader`), so a text
      with neither is not working; otherwise the whole text is read.

    A reading of the whole text is paid from the answer's :class:`_JoinBudget`; when it cannot be paid, the line is not joined and
    the refusal is counted (the parser names it in the report's unresolved issues). No answer of the recorded rounds comes near
    the budget; an answer that spends it is one built to make every join read all that came before."""

    __slots__ = ("lines", "header", "accuracy", "_tail", "_before_last", "_signs", "_end", "_run_answer")

    _END_KEEP = 24

    def __init__(self, first: str, accuracy: bool) -> None:
        self.lines = [first]
        self.header = False
        self.accuracy = accuracy
        self._tail = JoinedLine(first, mask=_unmasked)  # its working test reads the text unmasked
        self._signs = bool(_RELATION_SIGN_RE.search(first))
        self._before_last = ""  # the last characters of the text before the last line
        self._end = first[-self._END_KEEP:]
        self._run_answer: Optional[bool] = None

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    def add(self, line: str, accuracy: bool) -> None:
        self._before_last = self._end
        self.lines.append(line)
        self.accuracy = self.accuracy or accuracy
        self._tail.add(line)
        self._signs = self._signs or bool(_RELATION_SIGN_RE.search(line))
        self._end = (self._end + "\n" + line)[-self._END_KEEP:]
        if self._run_answer is not None and not ANNOTATION_RUN_CONTINUATION_RE.fullmatch("\n" + line):
            self._run_answer = None  # the run of annotations no longer ends the text

    def table_row(self) -> bool:
        """``_TABLE_ROW_RE.match(text)``."""
        return self._tail.table_row()

    def terminal(self) -> bool:
        """``_TERMINAL_PUNCT_RE.search(text.rstrip(":;"))``."""
        return self._tail.terminal()

    def colon_end(self) -> bool:
        """``text.rstrip().endswith((":", ";"))``."""
        return self._tail.colon_end()

    def connective_end(self, budget: _JoinBudget) -> Optional[bool]:
        """``_CONNECTIVE_END_RE.search(_strip_annotations(text))``; None when the reading it needs cannot be paid."""
        if self._run_answer is not None:
            return self._run_answer  # the text still ends with the trailing run of annotations its answer was read for
        last = self.lines[-1]
        if len(self.lines) == 1:
            answer = bool(_CONNECTIVE_END_RE.search(_strip_annotations(last)))
            self._keep_run(trailing_annotation_span(last), len(last), answer)
            return answer
        body = last[:-1] if last.endswith((".", ";", ",")) else last
        if _ANNOTATION_BARRIER_RE.search(body):
            # the trailing run, if any, lies after the last character no annotation holds: in the last line
            span = trailing_annotation_span(last)
            if span is None:
                return bool(_CONNECTIVE_END_RE.search(self._end))
            a, b = span
            rest = last[b:]
            answer = rest == "," if rest else bool(_CONNECTIVE_END_RE.search((self._before_last + "\n" + last[:a])[-self._END_KEEP:]))
            self._keep_run(span, len(last), answer)
            return answer
        if not _ANNOTATION_CLOSER_RE.search(body):
            # no annotation ends in the last line, so no run of them ends the text
            return bool(_CONNECTIVE_END_RE.search(self._end))
        text = self.text
        if not budget.pay(len(text)):
            return None
        answer = bool(_CONNECTIVE_END_RE.search(_strip_annotations(text)))
        self._keep_run(trailing_annotation_span(text), len(text), answer)
        return answer

    def _keep_run(self, span: Optional[tuple[int, int]], length: int, answer: bool) -> None:
        """Keep ``answer`` while the text ends with the trailing run ``span`` (of a text ``length`` long) and what is added goes on
        with it: the run's start, so the answer, stays the same."""
        self._run_answer = answer if span is not None and span[1] == length else None

    def working(self, budget: _JoinBudget) -> Optional[bool]:
        """``_is_working(mask_quotations(text))``; None when the reading it needs cannot be paid."""
        if len(self.lines) == 1:
            return _is_working(mask_quotations(self.lines[0]))
        if not self._signs and not self._tail.working():
            return False
        text = self.text
        if not budget.pay(len(text)):
            return None
        return _is_working(mask_quotations(text))


def _logical_lines(paragraph: str, state: Optional[_State] = None) -> list[tuple[str, bool, bool]]:
    """``(line, is_table_header, accuracy_marked)`` for each logical line of ``paragraph``: continuation lines joined to the
    line before them (each physical line's mark annotations removed first), table separator rows dropped. The logical line
    being read is a :class:`_LogicalLine`, so each rule reads what it needs of it once (integration gate 2); a join whose
    reading the answer's budget (``state.join_budget``; the paragraph's own when no state is given) cannot pay is refused and
    counted on ``state``."""
    raw = paragraph.split("\n")
    out: list[_LogicalLine] = []
    budget = state.join_budget if state is not None and state.join_budget is not None else _JoinBudget(len(paragraph))
    refused = 0
    for line in raw:
        if not line.strip():
            continue
        accuracy = _accuracy_marked(line)
        line = _strip_annotations(line) if not _ANNOTATION_ONLY_LINEAR_RE.fullmatch(line) else line
        if _TABLE_SEPARATOR_RE.match(line) and "-" in line:
            if out and out[-1].table_row():
                out[-1].header = True  # the row above a separator is the table's header
            continue
        if out and not _PART_LEAD_RE.match(line) and not _BULLET_RE.match(line) and not _TABLE_ROW_RE.match(line):
            prev = out[-1]
            joins: Optional[bool] = bool(_CONTINUATION_RE.match(line))
            if not joins:
                connective = prev.connective_end(budget)
                if connective is None:
                    joins = None
                elif connective and not prev.table_row():
                    joins = True
            if (joins is False and _SOFT_WRAP_NEXT_RE.match(line) and not prev.terminal() and not prev.colon_end()
                    and not _is_working(mask_quotations(line))):
                working = prev.working(budget)
                joins = None if working is None else not working
            if joins is None:
                refused += 1
            elif joins:
                prev.add(line.rstrip(), accuracy)
                continue
        out.append(_LogicalLine(line.rstrip(), accuracy))
    if state is not None:
        state.joins_refused += refused
    return [(ll.text, ll.header, ll.accuracy) for ll in out]


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
    joins_refused: int = 0           # joins of physical lines refused because their reading exceeded the answer's budget (_JoinBudget)
    join_budget: Optional[_JoinBudget] = None  # the answer's budget for the join rules' readings (set by parse_response)


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
    lines = _logical_lines(paragraph, state)
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
        if not body.strip() or _ANNOTATION_ONLY_LINEAR_RE.fullmatch(body):
            continue
        heading = header or (m is None and _line_heading(body, li < len(lines) - 1))
        line_units: list[_Unit] = []
        for piece, is_json in split_json_spans(body.strip()):
            sents = [piece] if is_json else [s.strip() for s in _SENT_RE.split(piece) if s.strip()]
            for s in sents:
                s = s if is_json else _strip_annotations(s)
                if not s or (not is_json and _ANNOTATION_ONLY_LINEAR_RE.fullmatch(s)):
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
    return [inner for _s, _e, inner in parser_quotation_spans(sentence) if len(inner.strip()) >= _MIN_QUOTE_CHARS]


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


class _View(Sequence):
    """A read-only, ascending, duplicate-free list of claim indices that shares sorted lists instead of copying them
    (integration gate 2): ``_View((items, start, stop), ...)`` is the union of the slices ``items[start:stop]``, each of an
    ascending list. Every conclusion of a paragraph rests on all the claims before it, every closing answer of a part on the
    eligible claims before it, every labelled answer of a line on the claims after it: a list of its own for each was n² entries
    ('Therefore x. ' * 8,000: 1.5 GB). A view is only read (iterated, sized, compared), never changed; the lists it shares only
    grow past the slices it reads."""

    __slots__ = ("_slices", "_items")

    def __init__(self, *slices: tuple[list[int], int, int]) -> None:
        self._slices = tuple(sl for sl in slices if sl[2] > sl[1])
        self._items: Optional[list[int]] = None

    def __iter__(self):
        if self._items is not None:
            return iter(self._items)
        if len(self._slices) == 1:
            items, a, b = self._slices[0]
            return itertools.islice(items, a, b)
        return self._merged()

    def _merged(self):
        last = None
        for j in heapq.merge(*(itertools.islice(items, a, b) for items, a, b in self._slices)):
            if j != last:
                yield j
                last = j

    def _list(self) -> list[int]:
        if self._items is None:
            # from the iterator itself: list(self) would ask len(self), which asks for this list
            self._items = [j for j in (self._merged() if len(self._slices) > 1 else iter(self))]
        return self._items

    def __bool__(self) -> bool:
        return bool(self._slices)

    def __len__(self) -> int:
        if len(self._slices) == 1:
            _items, a, b = self._slices[0]
            return b - a
        return len(self._list())

    def __getitem__(self, k):
        if len(self._slices) == 1 and not isinstance(k, slice):
            items, a, b = self._slices[0]
            if k < 0:
                k += b - a
            if not 0 <= k < b - a:
                raise IndexError(k)
            return items[a + k]
        return self._list()[k]

    def __eq__(self, other) -> bool:
        return list(self) == list(other) if isinstance(other, (list, tuple, _View)) else NotImplemented

    __hash__ = None  # type: ignore[assignment]

    def __repr__(self) -> str:
        return repr(list(self))


class _Earlier(_View):
    """The first ``n`` claims of a paragraph's list of claims (``_View((items, 0, n))``)."""

    __slots__ = ()

    def __init__(self, items: list[int], n: int) -> None:
        super().__init__((items, 0, n))


class _SupportIndex:
    """The supports of the units with an index of the claims each unit supports, so that a unit is withdrawn from every list
    that holds it without reading all the lists (integration gate 2: :meth:`GenericTextParser._part_answers` read every list
    for each part's answer, n² steps on an answer of thousands of parts). A withdrawal is recorded and applied to a list when the
    work is done (:meth:`settle`), in the list's own order, so the supports are those the reading of every list gave."""

    __slots__ = ("supports", "holders", "withdrawn")

    def __init__(self, supports: dict[int, list[int]]) -> None:
        self.supports = supports
        self.holders: dict[int, set[int]] = {}
        self.withdrawn: dict[int, set[int]] = {}
        for p, ss in supports.items():
            if isinstance(ss, list):
                for s in ss:
                    self.holders.setdefault(s, set()).add(p)

    def withdraw(self, i: int) -> None:
        """``i`` supports nothing: ``supports[p] = [s for s in supports[p] if s != i]`` for every list."""
        for p in self.holders.pop(i, ()):
            self.withdrawn.setdefault(p, set()).add(i)

    def _forget(self, p: int) -> None:
        """Settle the list ``p`` holds before it is replaced or removed, and take it out of the index."""
        old = self.supports.get(p)
        if old is None:
            return
        self.withdrawn.pop(p, None)
        if not isinstance(old, list):
            return  # a view (_View) is never indexed: it holds no answer, and only answers are withdrawn
        for s in old:
            held = self.holders.get(s)
            if held is not None:
                held.discard(p)

    def set(self, p: int, ss: list[int]) -> None:
        """``supports[p] = ss``."""
        self._forget(p)
        self.supports[p] = ss
        if isinstance(ss, list):
            for s in ss:
                self.holders.setdefault(s, set()).add(p)

    def pop(self, p: int) -> None:
        """``supports.pop(p, None)``."""
        self._forget(p)
        self.supports.pop(p, None)

    def settle(self) -> None:
        for p, gone in self.withdrawn.items():
            if p in self.supports:
                self.supports[p] = [s for s in self.supports[p] if s not in gone]
        self.withdrawn.clear()


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
        for k, u in enumerate(units):
            i = start + k
            sent = u.text
            core = cores[k]
            if note_paragraph or notes_flags[k]:
                roles[i] = "other"
                continue
            low = (core or sent).lower()
            opening_command = u.opening and (k == 0 or units[k - 1].line != u.line)  # "(b) Hence, ...": the question's command term
            consequence[i] = not opening_command and _is_consequence(mask_quotations(core or sent))
            caveat[i] = bool(_CAVEAT_RE.match(mask_quotations(core or sent)))
            if consequence[i] or (any(kw in low for kw in _JUDGE) and not opening_command):
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
        state = _State(join_budget=_JoinBudget(len(text)))
        para_units: list[list[_Unit]] = [_units_of(para, pi, state) for pi, para in enumerate(paragraphs)]
        flat: list[_Unit] = [u for units in para_units for u in units]
        if not flat:
            raise AdapterError("the specialist answer yields no sentences")
        if state.joins_refused:
            unresolved.append(f"{state.joins_refused} line(s) of the answer were not joined to the line before them: deciding the join would have "
                              f"read the logical line before them again beyond the parser's reading bound ({_JOIN_READ_PER_CHAR} characters per "
                              f"character of the answer and {_JOIN_READ_FLOOR:,} more), so each opens a claim of its own")

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
                    refs_of[i].append(SourceRef(document_id=doc, excerpt=ex[:2000]))
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
                                certainty=hedged_certainty(u.text) or "established",
                                advisory_verification_status=_SELF_REPORT if is_self_certification(u.text) else None))
        ids = [p["claim_id"] for p in pending]
        tail_id = _TAIL_CLAIM_ID  # the fold claim of an oversized answer keeps its fixed id (pinned by the History regressions)
        if len(pending) > _MAX_CLAIMS:
            head, tail = pending[: _MAX_CLAIMS - 1], pending[_MAX_CLAIMS - 1:]
            head.append(dict(claim_id=tail_id, claim_text=truncate_claim_text(" ".join(p["claim_text"] for p in tail)), claim_role="other", proposed_claim_kind="unknown", source_refs=[], assumptions=[], materiality="supporting", advisory_verification_status=None))
            unresolved.append(f"{len(tail)} sentences beyond the report's claim limit ({_MAX_CLAIMS}) were merged into claim {tail_id} and were not individually roled or checked")
            pending = head
        kept = {p["claim_id"] for p in pending}
        unit_of = {cid: i for i, cid in enumerate(ids)}
        kept_units = sum(1 for cid in ids if cid in kept)  # the first units: the folded ones come last

        def supporting(cid: str) -> list[str]:
            """The ids of the kept claims that support claim ``cid``, in claim order, at most the claim limit: read for the claims the
            report keeps only (integration gate 2: the ids of every unit's supports were listed first, n² of them for an answer of
            thousands of conclusions, 'Therefore x. ' * 8,000: 1.5 GB)."""
            i = unit_of.get(cid)
            if i is None or roles[i] == "other" or i not in supports:
                return []
            ss = supports[i]
            out: list[str] = []
            for s in (ss if isinstance(ss, _View) else sorted(set(ss))):  # a view is ascending and holds each claim once
                if s >= kept_units:
                    break  # the claims the report keeps are the first ones (the rest are folded into its last claim)
                if s != i and ids[s] in kept:
                    out.append(ids[s])
                    if len(out) == _MAX_CLAIMS:
                        break
            return out

        claims = [ClaimRecord(**base, **{**p, "supporting_claim_ids": supporting(p["claim_id"])}) for p in pending]
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
        if not u.is_json and (not _NUM_RE.search(u.text) or _NEGATIVE_CAVEAT_RE.search(u.text)) and is_source_caveat(u.text):
            return True  # 'My sources do not confirm the exact total, so the figure is given as "millions".': the History parser's caveat
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
            # in 2016, so the library caused the fall"), is its own point: material, as the History and English parsers read it,
            # so a warning the argument diagnosis names on it reaches the receipt as INT-ARG-001
            from ..adapters.markdown import states_own_reason
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
        if leads[first] in ("assumption", "diagram") or roles[first] == "judgement":
            return
        roles[first], material[first] = "point", True
        supports[first] = [i for i in live[1:] if roles[i] not in ("judgement",) and not consequence[i] and not caveat[i] and leads[i] not in ("assumption",)]

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
        layout = GenericTextParser._line_layout(flat)
        links = _SupportIndex(supports)
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
                run = GenericTextParser._first_working_run(flat, live, layout)
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
            if closing:
                # the claims a closing answer may rest on, listed once for the part (integration gate 2: each closing answer read
                # the whole part again, n² steps on a part of thousands of results). No closing answer's processing changes the
                # role of a claim that is no answer, so the lists hold for every closing answer of the part.
                eligible = [j for j in live if not answer[j] and leads[j] != "diagram" and roles[j] != "other"]
                anywhere = [j for j in eligible if flat[j].working or roles[j] == "evidence"]
                in_para: dict[int, list[int]] = {}
                for j in eligible:
                    in_para.setdefault(flat[j].para, []).append(j)
            for i in closing:
                # a closing answer rests on the claims before it in its paragraph and on the part's earlier lines of working and
                # the quotations they use, not on every remark the part made before it
                same = in_para.get(flat[i].para, [])
                earlier = _View((anywhere, 0, bisect.bisect_left(anywhere, i)), (same, 0, bisect.bisect_left(same, i)))
                # a closing answer rests on what came before it; it is no other claim's support
                links.withdraw(i)
                if roles[i] == "point" and i in supports:
                    links.pop(i)
                if earlier:
                    roles[i] = "point"
                    links.set(i, earlier)
            last_in_para: dict[int, int] = {}
            for j in live:
                last_in_para[flat[j].para] = j  # live is in claim order: the last claim of each paragraph
            after_in_para: dict[int, list[int]] = {}
            for i in opening_answers:
                if i in closing:
                    continue
                para = flat[i].para
                # a bare answer alone in its paragraph ("(-1, 3)"): what follows in the part justifies it, and the first
                # sentence of that justification is not a point of its own
                alone = not last_in_para.get(para, -1) > i
                if alone:
                    pool = [j for j in live if j > i]
                    later = [j for j in pool if not answer[j] and roles[j] != "judgement" and not consequence[j] and not caveat[j]
                             and leads[j] not in ("assumption", "diagram")]
                else:
                    # the answers of one line that a claim of their paragraph follows (integration gate 2: each read its paragraph
                    # again, n² steps on a line of thousands of labelled answers). Only the last answer of the line can be alone, and
                    # only an alone answer demotes a point, so the list holds for every answer of the line before it.
                    if para not in after_in_para:
                        after_in_para[para] = [j for j in live if flat[j].para == para and not answer[j] and roles[j] not in ("judgement", "point")
                                               and not consequence[j] and not caveat[j] and leads[j] not in ("assumption", "diagram")]
                    rest = after_in_para[para]
                    later = _View((rest, bisect.bisect_right(rest, i), len(rest)))
                links.withdraw(i)
                roles[i] = "point" if later or roles[i] in ("point", "analysis") else roles[i]
                links.set(i, later)
                if alone:  # a list without points (an answer that is not alone) demotes none
                    for j in later:
                        if roles[j] == "point":
                            roles[j], material[j] = ("quantitative" if _NUM_RE.search(flat[j].text) else "analysis"), False
                            links.pop(j)
        links.settle()

    @staticmethod
    def _line_layout(flat: list[_Unit]) -> tuple[dict[int, int], dict[int, set[int]]]:
        """``(units per line, lines per paragraph)`` of the units, read once for every part (integration gate 2)."""
        per_line: dict[int, int] = {}
        para_lines: dict[int, set[int]] = {}
        for u in flat:
            per_line[u.line] = per_line.get(u.line, 0) + 1
            para_lines.setdefault(u.para, set()).add(u.line)
        return per_line, para_lines

    @staticmethod
    def _first_working_run(flat: list[_Unit], live: list[int], layout: Optional[tuple[dict[int, int], dict[int, set[int]]]] = None) -> list[int]:
        """The part's first run of working: the working claims of the consecutive paragraphs, from the first that holds a line
        of working, that each hold one. A line of working stands on a line of its own or in a line-structured block; an
        equation inside a sentence of a prose paragraph is the prose's, and a diagram line is description, not working.
        ``layout`` is :meth:`_line_layout` of ``flat``, given by a caller that asks for every part (integration gate 2: each part
        read the lines of every unit of the answer again, n² steps on an answer of thousands of parts, '1. x' on each of
        3,200 lines: 8 s of a 9.6 s Economics receive)."""
        by_para: dict[int, list[int]] = {}
        for i in live:
            by_para.setdefault(flat[i].para, []).append(i)
        per_line, para_lines = layout if layout is not None else GenericTextParser._line_layout(flat)
        structured = {p for p in by_para if len(para_lines.get(p, ())) > 1}
        run: list[int] = []
        started = False
        for para in sorted(by_para):
            working = [i for i in by_para[para] if flat[i].working and flat[i].lead not in ("diagram", "heading")
                       and (para in structured or per_line[flat[i].line] == 1)]
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
            live: list[int] = []  # the paragraph's claims that are not 'other', up to the unit read (roles do not change here)
            for i in range(start, end):
                if not ((roles[i] != "judgement" and not consequence[i]) or answer[i]):
                    # a point never rests on a judgement or a consequence, so the edge from an earlier claim cannot close a cycle
                    if live:
                        supports[i] = _Earlier(live, len(live))
                if roles[i] != "other":
                    live.append(i)
