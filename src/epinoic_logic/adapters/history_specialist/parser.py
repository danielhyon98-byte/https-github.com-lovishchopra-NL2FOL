"""Heuristic parser for History specialist responses written with the pack's core
operation: Claim -> Evidence -> Analysis -> Judgement -> Link (Response application §3,
Structures §5). Sentences are assigned roles from surface cues; support links follow the
argument and never form a cycle: the point of each body paragraph rests on the paragraph's
evidence, analysis, counter-case and reported views (never on a judgement or link), and each
judgement or link rests on the point and the claims before it (never on a later judgement),
so the paragraph's verdict is an argument the translator can formalize. Heuristic by design:
the generic structured adapter is the contract future agents should emit directly.

Paragraph classification is decided by content, never by paragraph count alone:

* a ``note`` paragraph is one whose sentences are ALL labels about the text (a
  from-memory disclaimer, a task note that the syllabus version or level was not
  given, a self-certification line, a pasted JSON fragment), or a short undated aside
  with no argument cue; its claims are roled ``other`` and are never material, and it
  does not make the answer "multi-paragraph";
* with three or more prose paragraphs, the first is the ``intro`` only when it has
  no dated item while a later paragraph does, and the last is the ``conclusion`` only
  when it has two or more sentences or opens with a concluding cue;
* everything else is a ``body`` paragraph whose first substantive sentence is the point.

Inside a body paragraph a sentence's function is read before its surface (:func:`classify`):
a link lead ('Against this background, ...', 'Against that toll, ...') is a ``link`` and a stated
verdict ('The turning point was 1930.', 'The 1840s were the most decisive decade.') or the
criterion of one ('Measured by what the network could do, ...') a ``judgement``, all material
whatever they date or quote; an undated sentence carrying one of the channel's verdict cues is a
``judgement`` too; a note on how the answer was composed ('The historical setting is my own
addition, not part of that paragraph.', :func:`is_provenance_note`) is ``other``; a counter-case
is ``counter_evidence`` dated or not (unless a judgement cue weighs it), and the dated sentence
right after an undated counter-case statement is its counter evidence; only then does a dated
item make a sentence ``evidence``, and a year that only names an event ('the 1923 crisis')
dates no statement. A pasted JSON receipt glued to the prose is one ``other`` sentence (the
shared splitter never cuts inside it), so none of its fragments becomes a claim.

Inside a body paragraph only the sentence that certifies the answer's own verification
or is shaped like a receipt becomes a note (role ``other``, its self-report in the
advisory field); the paragraph's other sentences keep their roles, and the demotion is
recorded as an unresolved issue naming the sentence. A substantive sentence that carries
the method's own label inline ("... fell to about 41 in July 1932 (figures from memory;
check your notes)", "From memory, the mark stood at ...", ", from memory about 800 million
gold marks,") keeps its role and eligibility: ``markdown.split_note_clauses`` removes the
label before the sentence is classified and the label is recorded once in the claim's
assumptions; only a sentence whose core is empty is a note. Dated claims made under a
from-memory label (anywhere in the answer or inline) are capped at certainty ``probable``.
A claim the writer hedges is recorded with the hedge's certainty: this parser's own cues
("suggests", "may have", "can be read as") and the hedges every parser reads outside
quotations (``markdown.hedged_certainty``: "probably", "possibly", "might have", "most
likely", ...), the weaker of the two.

A sentence whose subject is a peer specialist's view ("The English specialist argues that
...", "The English specialist's phrase '...' fits that record") is roled ``perspective``:
it is the colleague's claim, not the History specialist's own, so its certainty is capped
at ``probable`` and the attribution is recorded as an assumption.

Quotations are recognised in straight, curly or mixed double marks, guillemets and
delimited single marks of two or more words, after pasted JSON fragments are removed from
the sentence (their strings are never quotations). A quotation is attributed to the
supplied text its sentence names (author, surname, title, or a peer specialist by name)
when that text holds the words, else to a text that holds them; a quotation held by no
text is attributed to the one text the sentence names (so the hub reports the credit) and
otherwise to NO text: it is recorded as an assumption so the core pack can report it as
unverifiable (``CORE-SRC-003``). It is never attributed to the first supplied text merely
because that text came first. The rule is the shared one of
:func:`~epinoic_logic.adapters.sources.attribute_excerpt`, which the English and generic
parsers apply too (re-exported here as ``attribute_excerpt``).

Markdown headings, code fences and emphasis are removed before segmentation, sentences
are split with the shared abbreviation-aware splitter (``c.``, ``approx.``, initials never
end a sentence), a newline followed by a list marker ends a sentence, and
``original_response`` is always the verbatim text.
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from ...ir.schema import SourceRef
from ...translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text
from ..base import AdapterError
from ..english_specialist.parser import documents_named
from ..markdown import (MEMORY_LABEL_RE, dangling_quote_offset, find_quotation_spans, hedged_certainty, is_memory_label, is_self_certification,  # noqa: F401
                        split_list_items, split_note_clauses, strip_markup, truncate_claim_text, undelimited_quote_span)
from ..sources import attribute_excerpt, check_excerpt  # noqa: F401  (attribute_excerpt: the shared rule, re-exported here)
from .chronology import MONTH_YEAR_RE as _MONTH_YEAR_RE  # noqa: F401  (re-exported for callers of the old name)
from .chronology import chronology_findings_in, chronology_relations, date_in_aside, month_index  # noqa: F401
from .sentences import split_sentences as _split_sentences, strip_json_spans

ParagraphKind = Literal["intro", "body", "conclusion", "note"]

_DATE_RE = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_FIGURE_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:per cent|percent|%|million|billion|trillion|thousand|seats|votes|laws|decrees|per thousand)\b|\b\d{1,3}(?:,\d{3})+\b", re.IGNORECASE)
_MONTH_NAMES = "January|February|March|April|May|June|July|August|September|October|November|December"
_DAY_MONTH_RE = re.compile(rf"\b\d{{1,2}}\s+(?:{_MONTH_NAMES})\b|\b(?:{_MONTH_NAMES})\s+\d{{1,2}}\b")
#: Cues of a counter-case, a judgement, a criterion, an analysis step and a link, shared with the structural checks.
COUNTER_CUES = ("the counter-case", "counter-case is", "counter-argument is", "the strongest objection", "against this", "the distinction is right", "however",
                "on the other hand", "it could be argued")
CRITERION_CUES = ("by the criterion", "by the criteria", "criterion of", "criteria of", "weighed by", "measured by", "judged by", "by the test of", "by the standard of", "by the measure of")
JUDGEMENT_CUES = ("by the criterion", "by the criteria", "criteria of", "weighed by", "weighs", "weighs more", "holds for", "decisive even if", "remains the precondition", "was therefore responsible", "fails, because",
                  "does not shift the weight", "necessary; it was not sufficient", "necessary but not sufficient", "to a degree",
                  "on balance", "mattered most", "matters most", "outweigh", "more significant than", "carries the greater weight", "carry the greater weight")
#: The verdict cues the channel reads for a position on degree (INT-REQ-008): the channel's own tuple (``channel/cues.py`` has no
#: imports, so there is no cycle), so the parser and the channel never disagree about what a verdict looks like.
try:
    from ...channel.cues import VERDICT_CUES
except ImportError:  # pragma: no cover - the channel always ships the module; the fallback keeps the parser importable alone
    VERDICT_CUES = ("therefore", "thus", "to a large extent", "to a great extent", "to a limited extent", "to a lesser extent", "to some extent", "to a considerable extent",
                    "to a degree", "decisive", "necessary but not sufficient", "necessary and not sufficient", "necessary but sufficient", "outweigh", "on balance",
                    "more significant than", "more important than", "more decisive than", "less significant than", "less important than", "matters most", "mattered most",
                    "the most significant", "the most important", "the most decisive", "holds for", "does not hold", "fails")
_COUNTER = COUNTER_CUES
_JUDGEMENT = JUDGEMENT_CUES
_ANALYSIS = ("mattered because", "the mechanism was", "this shows", "which shows", "this mattered", "meant that", "so that", "revealed", "explains why", "this matters")
_LINK = ("therefore", "thus", "in sum", "ultimately")
#: A sentence that ties the paragraph's evidence back to the question or to a peer's text: a link, whatever it quotes or dates.
_LINK_LEADS = ("against this background", "against that background", "in this light", "in that light", "seen in this light", "read against", "seen against",
               "set against this", "in this context", "in that context", "this context explains", "this background explains", "this is why")
#: 'Against that toll, ...', 'Set against this record, ...', 'Seen against these losses, ...': a demonstrative noun phrase after
#: 'against' ties the sentence back to what the paragraph has just set out, so the sentence is a link. A bare 'Against this, ...'
#: (no noun) is a counter-case lead and stays one.
_LINK_LEAD_RE = re.compile(r"^(?:(?:set|seen|read|measured|weighed)\s+)?against\s+(?:this|that|these|those|such)\s+(?!is\b|was\b|are\b|were\b)[a-z][a-z'’-]*(?:\s+[a-z][a-z'’-]*)?\s*,", re.IGNORECASE)
#: A sentence that states the verdict a request asks for ('The turning point was 1930.', 'X mattered most', 'The 1840s were the most
#: decisive decade.', 'The most decisive decade was the 1840s.', 'The 1840s saw the most decisive expansion.'): a judgement, dated or
#: not. The copula may be singular or plural ('was', 'were', 'is', 'are', 'proved', 'remained', 'became'), or a verb of standing as
#: ('stands out as', 'emerged as', 'counts as', 'ranks as') before the turning point, a verdict noun or the watershed, and the noun a period
#: ('decade', 'period', 'phase', 'stage', 'era') or a request's judgement noun ('expansion', 'change', 'development', 'factor').
#: Adjectives of a verdict: with 'most' any degree adjective ('the most significant change'); without it only those that are a verdict
#: by themselves ('the decisive decade', 'the pivotal year'), so 'the significant growth was ...' stays a description.
_VERDICT_ADJ_MOST = r"(?:decisive|pivotal|critical|crucial|important|significant|consequential|influential|formative|transformative|far-reaching)"
_VERDICT_ADJ_BARE = r"(?:decisive|pivotal|critical|crucial|key|formative|defining)"
_VERDICT_NOUN = (r"(?:years?|decades?|period|phase|stage|era|moment|month|factor|cause|event|turning point|break|reason|effect|consequence|"
                 r"expansion|growth|change|development|step|shift|advance|influence|driver|force)")
_VERDICT_ADJ_NOUN = rf"(?:(?:single\s+)?most\s+{_VERDICT_ADJ_MOST}|{_VERDICT_ADJ_BARE})\s+{_VERDICT_NOUN}"
_VERDICT_STATEMENT_RE = re.compile(
    r"\b(?:the|a)\s+(?:real\s+|true\s+|decisive\s+|key\s+|critical\s+|crucial\s+|main\s+)?turning[- ]point\s+(?:was|were|came|is|lay|fell)\b"
    r"|\b(?:was|were|is|are|marked|became|proved|(?:stands?|stood)\s+out\s+as|(?:emerges?|emerged|counts?|counted|ranks?|ranked)\s+as)\s+(?:the|a)\s+"
    r"(?:real\s+|true\s+|decisive\s+|key\s+|critical\s+|crucial\s+|main\s+)?turning[- ]points?\b"
    rf"|\bthe\s+{_VERDICT_ADJ_NOUN}\s+(?:of\s+[^,;.]{{1,60}}?\s+)?(?:was|were|is|are|came)\b"
    rf"|\b(?:was|were|is|are|proved|remained|became|has\s+been|have\s+been|marked|represented|made|(?:stands?|stood)\s+out\s+as|(?:emerges?|emerged|counts?|counted|ranks?|ranked)\s+as)"
    rf"\s+(?:the|its|their)\s+{_VERDICT_ADJ_NOUN}\b"
    rf"|\b(?:was|were|is|are|proved|remained|became)\s+(?:(?:truly|genuinely|clearly|plainly|therefore|thus|itself|then)\s+)?{_VERDICT_ADJ_BARE}\s*(?:[.;!?,]|$)"
    r"|\bthe\s+(?:year|decade|moment|point|hour|period|turn)\s+of\s+decision\s+(?:was|were|came|is|fell)\b"
    r"|\bthe\s+(?:real|true|decisive|key|critical|crucial|main|great|major)\s+(?:break|shift|departure|watershed|rupture)\s+(?:came|was|fell|lay|occurred|happened)\b"
    r"|\b(?:was|were|is|are)\s+the\s+(?:single\s+)?most\s+(?:important|significant|decisive)\b"
    rf"|\b(?:saw|brought|witnessed|marked|produced|delivered)\s+the\s+(?:single\s+)?most\s+{_VERDICT_ADJ_MOST}\s+[a-z]+"
    r"|\b(?:the\s+)?watershed\s+(?:was|were|came)\b"
    r"|\b(?:was|were|is|are|marked|(?:stands?|stood)\s+out\s+as|(?:emerges?|emerged|counts?|counted|ranks?|ranked)\s+as)\s+(?:the|a)\s+watershed\b"
    r"|\b(?:mattered|matters)\s+most\b",
    re.IGNORECASE)
#: A sentence that opens by naming the criterion of a verdict ('Measured by what the network could do, ...', 'Judged by the
#: criterion of capacity, ...'): the judgement's criterion, roled a judgement whatever it dates.
_CRITERION_LEAD_RE = re.compile(r"^(?:(?:but|and|yet|so|thus|on\s+balance)[,\s]+)?(?:measured|judged|weighed|assessed)\s+(?:by|in\s+terms\s+of)\b"
                                r"|^by\s+(?:the|this|that|any)\s+(?:criterion|criteria|measure|standard|test)\b", re.IGNORECASE)
#: The channel's verdict cues as one word-bounded pattern: an undated sentence that the channel counts as a verdict (INT-REQ-008 reads an
#: analysis claim with one of these as a position on degree) is roled a judgement here, so the hub and the parser never disagree.
_VERDICT_CUE_RE = re.compile(r"\b(?:" + "|".join(re.escape(c) for c in sorted(VERDICT_CUES, key=len, reverse=True)) + r")\b", re.IGNORECASE)
#: A year used as a modifier ('the 1923 crisis', 'the September 1930 election'): it names an event, it does not date a statement.
_ATTRIBUTIVE_YEAR_RE = re.compile(
    r"\b(?:the|a|an|its|their|this|that|his|her)\s+(?:(?:early|late|mid)[\s-]+)?(?:(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+)?"
    r"(?:1[0-9]{3}|20[0-9]{2})\s+(?=[a-z])")
_CONCLUSION_CUES = _LINK + ("overall", "in conclusion", "to conclude", "on balance")
_ARGUMENT_CUES = _COUNTER + _JUDGEMENT + _ANALYSIS + _LINK + ("decisive", "responsible", "extent", "degree", "because", "caused")
_PERSPECTIVE = ("historians who", "one historian", "some historians", "others describe", "historians argue", "has argued")
#: A sentence whose subject is a peer specialist's view: 'The English specialist argues that ...', 'The English specialist's phrase "..." fits'.
_PEER_ATTRIBUTION_RE = re.compile(
    r"^(?:(?:as|yet|but|however|indeed|similarly|likewise|further|moreover|finally|first|second|third|here|and|so)[,\s]+)?"
    r"(?:the|my|our)\s+(?:[a-z]+(?:[\s-][a-z]+)?\s+)?(?:specialist|colleague|peer)(?:'s|’s)?\s+"
    r"(?:argues?|argued|notes?|noted|writes?|wrote|describes?|described|says?|said|states?|stated|claims?|claimed|observes?|observed|suggests?|suggested|identifies|identified|"
    r"points?\s+out|pointed\s+out|calls?|called|reads?|presents?|presented|concludes?|concluded|holds?|held|maintains?|maintained|contends?|contended|"
    r"supplies|supplied|provides?|provided|offers?|offered|frames?|framed|"
    r"phrase|phrasing|claim|point|paragraph|reading|account|words?|view|argument|analysis|verdict|conclusion)\b",
    re.IGNORECASE,
)
#: A sentence about how the answer was composed, not about its subject ('The historical setting is my own addition, not part of
#: that paragraph.', 'The judgement on which decade saw the most decisive expansion is from memory as well; verify it before use.',
#: 'The English specialist's paragraph is from the hub; I have not checked its quotations.'): its subject is the answer, one of its
#: parts or a received report, and its predicate is authorship or provenance. Such a sentence is a note (role ``other``): never the
#: paragraph's point, never material, never addressing a request item.
_PROVENANCE_SUBJECT = (r"(?:the|this|my|our|that|these|those)\s+(?:[a-z'’-]+\s+){0,2}?"
                       r"(?:setting|context|background|judgement|judgment|verdict|conclusion|outline|answer|paragraph|response|summary|account|framing|"
                       r"additions?|section|reading|analysis|interpretation|report|material|points?|claims?|figures?|dates?|numbers?|statistics|quotations?|evidence)"
                       r"(?:\s+(?:on|of|about|for|in|above|below|here|given|that\s+follows?)\b[^,;:]{0,120}?)?")
_PEER_REPORT_SUBJECT = (r"(?:the|my|our)\s+(?:[a-z]+\s+)?(?:specialist|colleague|peer)(?:'s|’s)\s+"
                        r"(?:paragraph|report|reading|analysis|account|words|quotations?|text|answer|contribution|material)")
_PROVENANCE_PREDICATE = (r"(?:is|are|was|were)\s+(?:also\s+|entirely\s+|wholly\s+|all\s+|likewise\s+|itself\s+|simply\s+)?"
                         r"(?:(?:my|our)\s+own(?:\s+(?:addition|additions|work|view|judgement|judgment|reading|inference|framing|contribution|interpretation|summary|context|gloss))?"
                         r"|mine|ours"
                         r"|(?:an?|my|our)\s+(?:own\s+)?(?:addition|additions|supplement|gloss)"
                         r"|not\s+(?:part\s+of|from|in|taken\s+from|drawn\s+from|stated\s+in|given\s+in)\s+[^,;:]{1,60}"
                         r"|from\s+(?:memory|recollection|the\s+hub|my\s+own\s+(?:knowledge|recollection|reading|memory)|that\s+paragraph|that\s+report"
                         r"|the\s+(?:[a-z]+\s+)?(?:specialist|colleague|peer)(?:'s|’s)?(?:\s+(?:paragraph|report|text))?)"
                         r"|(?:taken|drawn|quoted|relayed|forwarded|supplied|received|passed\s+on)\s+(?:from|through|by|via)\s+[^,;:]{1,60}"
                         r")(?:\s+(?:as\s+well|too|also|alone))?")
_DISCOURSE_LEAD = r"(?:(?:but|and|so|also|note(?:\s+that)?|please\s+note(?:\s+that)?)[,:\s]+)?"
_PROVENANCE_CLAUSE_RE = re.compile(rf"^{_DISCOURSE_LEAD}(?:{_PEER_REPORT_SUBJECT}|{_PROVENANCE_SUBJECT})\s+{_PROVENANCE_PREDICATE}$", re.IGNORECASE)
#: Clauses that may stand beside a provenance clause in a note: ', not part of that paragraph', 'I have not checked its quotations',
#: 'verify it before use', 'check it against your notes'.
_NOT_PART_RE = re.compile(r"^(?:and\s+|but\s+)?(?:it\s+is\s+|they\s+are\s+)?not\s+(?:part\s+of|from|in|taken\s+from|drawn\s+from)\s+[^,;:]{1,60}$", re.IGNORECASE)
_NO_CHECK_RE = re.compile(r"^(?:and\s+|but\s+|so\s+)?(?:I|we)\s+(?:have\s+not|haven't|did\s+not|didn't|could\s+not|couldn't|cannot|can't)\s+"
                          r"(?:yet\s+)?(?:checked|verified|confirmed|check|verify|confirm|seen|read)\b[^,;:]{0,80}$", re.IGNORECASE)
_CHECK_IT_RE = re.compile(r"^(?:and\s+|so\s+|please\s+)?(?:verify|check|confirm|treat)\s+(?:it|them|this|these|that|those)\b[^,;:]{0,80}$", re.IGNORECASE)
_NOTE_CLAUSE_SPLIT_RE = re.compile(r"\s*(?:;|,|\s[-–—]\s|—|–)\s*")
#: A bare note lead ('Note:', 'N.B.', 'Next step:', 'Confidence:', 'Limit:', 'Caveat:'): a sentence it opens is a note, and a paragraph
#: whose first sentence it opens is a note paragraph as a whole, whatever its length, dates or figures. 'Note on ...:' and 'Note that ...'
#: (no colon) introduce substance and are not bare leads.
_NOTE_LEAD_RE = re.compile(r"^[\s*_>#-]*(?:(?:please\s+)?note|notes|nb|n\.\s?b\.|next\s+steps?|confidence|limits?|limitations?|caveats?|sourcing)\s*[:.]?(?<=[:.])"
                           r"|^[\s*_>#-]*(?:please\s+)?note\s*:", re.IGNORECASE)
#: A caveat about the answer's own sources or library: 'my sources do not confirm the exact emigration total', 'the textbook library and
#: MyLib were unavailable', 'no approved source here confirms the vote share'. Its subject is the answer's sources, not the past.
_SOURCE_SUBJECT = (r"(?:(?:my|our|the)\s+(?:own\s+)?(?:available\s+)?(?:sources?|notes|references|library|libraries|textbooks?(?:\s+library)?|knowledge\s+documents?)"
                   r"(?:\s+(?:here|available(?:\s+to\s+me)?|I\s+(?:have|had|used)))?|(?:the\s+)?(?:textbook\s+library|MyLib)(?:\s+and\s+(?:the\s+)?(?:textbook\s+library|MyLib))?"
                   r"|no\s+(?:approved\s+|available\s+|supplied\s+)?(?:source|reference|textbook)s?(?:\s+(?:here|available|I\s+have))?)")
_SOURCE_CAVEAT_RE = re.compile(
    rf"^(?:(?:but|and|so|however|also)[,\s]+)?{_SOURCE_SUBJECT}\s+"
    r"(?:(?:do|does|did|could|can)\s*(?:not|n['’]t)\s+(?:confirm|verify|give|state|record|cover|support|include)|cannot\s+(?:confirm|verify)|confirms?|verif(?:y|ies)"
    r"|(?:is|are|was|were)\s+(?:not\s+)?(?:unavailable|available|supplied|accessible|consulted)|(?:has|have|had)\s+not\s+been\s+(?:checked|confirmed|verified|available))\b",
    re.IGNORECASE)
#: The figure a caveat says the answer gives in its place: a quoted word ('the figure is given as 'millions'').
_QUOTED_TERM_RE = re.compile(r"(?<![\w])['‘\"“]([^'’\"”\n]{2,40})['’\"”](?![\w])")


def has_note_lead(sentence: str) -> bool:
    """True when ``sentence`` opens with a bare note lead ('Note:', 'N.B.', 'Next step:', 'Confidence:', 'Limit:', 'Caveat:'), quotations
    masked first, so a quoted 'Note:' is the quoted text's."""
    return bool(_NOTE_LEAD_RE.match(_mask_quotations(sentence)))


def is_source_caveat(sentence: str) -> bool:
    """True when ``sentence`` opens with a caveat about the answer's own sources or library ('My sources do not confirm the exact emigration
    total, so the figure is given as 'millions'; check the total in your textbook before quoting it.', 'The textbook library and MyLib were
    unavailable in this session, so these points rest on the supplied data') and nothing after the caveat states a dated item or a figure:
    a sentence that goes on to state one ('..., but about 3 million left between 1949 and 1961') keeps its substance."""
    masked = _mask_quotations(sentence).strip()
    core = re.sub(r"^[\s*_>#-]*(?:(?:please\s+)?note|nb|n\.\s?b\.|caveat|sourcing)\s*:\s*", "", masked, flags=re.IGNORECASE)
    m = _SOURCE_CAVEAT_RE.match(core)
    if m is None:
        return False
    rest = core[m.end():]
    clause_end = re.search(r"[,;]|\s(?:so|but|and)\s", rest)
    after = rest[clause_end.start():] if clause_end else ""
    return not has_dated_item(after)


def caveat_terms(sentence: str) -> list[str]:
    """The figure a source caveat says the answer gives in its place: its quoted words ('so the figure is given as 'millions'' ->
    'millions'). What the caveat says is not confirmed ('the 1924 vote share') is no figure the answer states, so it names no claim."""
    terms = [inner.strip() for _s, _e, inner in find_quotation_spans(sentence) if inner.strip()]
    terms += [m.group(1).strip() for m in _QUOTED_TERM_RE.finditer(sentence)]  # a single quoted word ('millions') is a term, not a quotation
    return list(dict.fromkeys(t for t in terms if t))


def is_provenance_note(sentence: str) -> bool:
    """True when ``sentence`` speaks only of how the answer was composed: its subject is the answer,
    its setting, its judgement, its figures or a received report ('The historical setting', 'The
    judgement on which decade ...', 'The English specialist's paragraph'), its predicate is authorship
    or provenance ('is my own addition', 'is not part of that paragraph', 'is from memory as well', 'is
    from the hub'), and every other clause is a note too ('verify it before use', 'I have not checked
    its quotations'). Quotations are masked first; a sentence that also asserts something about its
    subject ('..., and it shows that ...') is not a note."""
    masked = _mask_quotations(sentence).strip().rstrip(".!?\"'”’) ").strip()
    if not masked or len(masked) > 400:
        return False
    clauses = [c.strip() for c in _NOTE_CLAUSE_SPLIT_RE.split(masked) if c.strip()]
    found = False
    for clause in clauses:
        if _PROVENANCE_CLAUSE_RE.match(clause):
            found = True
        elif not (_NOT_PART_RE.match(clause) or _NO_CHECK_RE.match(clause) or _CHECK_IT_RE.match(clause) or not split_note_clauses(clause)[0]):
            return False
    return found


_ESTABLISHED = ("shows", "establishes", "demonstrates", "made", "led to", "was decisive", "proves", "was responsible")
_PROBABLE = ("suggests", "indicates", "is consistent with", "points to", "arguably")
_POSSIBLE = ("can be read as", "may have", "some historians argue", "it is possible that", "perhaps")
_MIN_SUBSTANTIVE_WORDS = 25   # a paragraph this short (and undated) does not make the answer multi-paragraph
_MAX_ASIDE_WORDS = 12         # a one-sentence undated line without an argument cue is an aside, not a claim
_MIN_QUOTE_CHARS = 4
_MAX_CLAIMS = 512
#: The roles that support a paragraph's point: what it rests on, never its verdict or its link back to the question.
_POINT_SUPPORT_ROLES = frozenset({"evidence", "analysis", "counter_evidence", "perspective"})
_TAIL_CLAIM_ID = "h.tail"
_SELF_REPORT = "self-certified in the response text"
_CERTAINTY_ORDER = ("established", "probable", "possible")


def _word_count(text: str) -> int:
    return len(text.split())


def split_sentences(paragraph: str) -> list[str]:
    """Sentence split that does not break after abbreviations ('c.', 'approx.', 'p.') or
    initials such as 'A. J. P.'; a newline followed by a list marker ends a sentence and
    the marker is dropped; a JSON fragment glued to prose is its own sentence."""
    out: list[str] = []
    for item in split_list_items(paragraph):
        out.extend(_split_sentences(item.strip()))
    return out


def has_dated_item(sentence: str) -> bool:
    return bool(_DATE_RE.search(sentence) or _FIGURE_RE.search(sentence) or _DAY_MONTH_RE.search(sentence))


def is_self_report(sentence: str) -> bool:
    """Verification-status language, a receipt-shaped fragment, or a sentence whose subject
    is the answer itself with a checking/accuracy predicate (``markdown.is_self_certification``)."""
    return is_self_certification(sentence)


def is_note_sentence(sentence: str) -> bool:
    """A sentence that is nothing but a label about the text: a self-report, a sentence opened by a
    bare note lead ('Note:', 'Limit:', 'Confidence:', :func:`has_note_lead`), a caveat about the
    answer's own sources or library (:func:`is_source_caveat`), a sentence whose substance is empty
    once its from-memory / task-note clauses are removed, or a note on how the answer was composed
    (:func:`is_provenance_note`: 'The historical setting is my own addition').
    A substantive sentence with an inline label is NOT a note (see :func:`split_note_clauses`)."""
    if is_self_report(sentence) or has_note_lead(sentence) or is_source_caveat(sentence):
        return True
    core, _notes = split_note_clauses(sentence)
    return not core or is_provenance_note(sentence)


def is_peer_attribution(sentence: str) -> bool:
    """True when the sentence's subject is a peer specialist's view ('The English specialist
    argues that ...'); a sentence that merely cites the peer mid-way ('..., bearing out the
    English specialist's claim that ...') is the History specialist's own."""
    return bool(_PEER_ATTRIBUTION_RE.match(sentence.strip()))


def is_note_paragraph(paragraph: str) -> bool:
    """The paragraph opens with a bare note lead ('Note:', 'N.B.', 'Next step:', 'Confidence:',
    'Limit:'), whatever its length, dates or figures; or all sentences are labels (from-memory
    disclaimers, task notes, source caveats, self-reports, JSON fragments); or the paragraph is a
    short undated aside with no argument cue. One
    self-report inside a substantive paragraph does NOT make the paragraph a note: only
    that sentence is demoted (see ``parse_response``)."""
    sentences = split_sentences(paragraph)
    if not sentences:
        return False
    if has_note_lead(sentences[0]) and not re.match(r"^[\s*_>#-]*note\s+on\b", sentences[0], re.IGNORECASE):
        return True  # 'Note: ...', 'Limit: ...', 'Confidence: ...' opening the paragraph: a note whatever its length, dates or figures
    if all(is_note_sentence(s) for s in sentences):
        return True
    low = paragraph.lower()
    return len(sentences) == 1 and _word_count(paragraph) < _MAX_ASIDE_WORDS and not has_dated_item(paragraph) and not any(c in low for c in _ARGUMENT_CUES)


def certainty_of(sentence: str, *, from_memory: bool = False, attributed: bool = False) -> str:
    """Agent-stated certainty from hedging cues (this parser's own, and the writer's hedges every parser reads outside
    quotations, ``markdown.hedged_certainty``: "probably", "possibly", "might have", "most likely", ...; the weaker of the
    two); a claim made under a from-memory label (``from_memory``: the sentence's own inline label, dated or not, or an
    answer-wide label for a dated claim) or a view attributed to a peer (``attributed``) is capped at ``probable``, since
    the specialist itself says the item is unverified recollection or a colleague's reading."""
    low = sentence.lower()
    if any(c in low for c in _POSSIBLE):
        level = "possible"
    elif any(c in low for c in _PROBABLE):
        level = "probable"
    else:
        level = "established"
    hedged = hedged_certainty(sentence)
    if hedged is not None and _CERTAINTY_ORDER.index(hedged) > _CERTAINTY_ORDER.index(level):
        level = hedged
    if (from_memory or attributed) and level == "established":
        level = "probable"
    return level


#: Causal or evaluative words that make a sentence a claim rather than a bare dated fact ('a major but partial cause of ...'), and
#: argument verbs of periodisation and shaping ('came in phases', 'gave the network its shape', 'transformed').
CLAIM_WORD_RE = re.compile(
    r"\b(?:responsible|because|caused?|causes|causing|led|leads?|made|makes?|turned|created|decisive|major|minor|partial|partly|significant|important|mainly|primarily|"
    r"chiefly|largely|extent|degree|therefore|thus|explains?|shows?|reveals?|mattered|matters|crucial|central|key|chief|principal|considerable|limited|ultimately|"
    r"undermined|weakened|strengthened|enabled|allowed|forced|ensured|meant|reason|consequence|result(?:ed)?|effect|impact|transformed|precondition|"
    r"phases?|stages?|shape[sd]?|shaping|formative|defined|defining|pattern|transform(?:s|ing|ation)?|reshaped|remade|drove|driven|accelerated|"
    r"slowed|marked|dominated|determined|decided|paved|laid|founded|established)\b", re.IGNORECASE)
#: A year range or a decade that sets the scope of a claim ('between 1830 and 1870', 'from 1928 to 1941', 'in the 1840s'): it dates
#: the period the claim is about, not an occurrence, so it does not make the sentence a bare dated fact.
_SCOPE_RANGE_RE = re.compile(r"\b(?:between|from)\s+(?:about\s+|c\.\s+)?(?:1[0-9]{3}|20[0-9]{2})\s+(?:and|to|until|till)\s+(?:about\s+|c\.\s+)?(?:1[0-9]{3}|20[0-9]{2})\b"
                             r"|\b(?:1[0-9]{3}|20[0-9]{2})\s*[-–]\s*(?:1[0-9]{3}|20[0-9]{2}|[0-9]{2})\b|\b(?:the\s+)?(?:1[0-9]{2}0|20[0-9]0)s\b", re.IGNORECASE)


def opens_with_fact(sentence: str) -> bool:
    """A sentence that states only a dated fact: dated (not merely naming 'the 1923 crisis', and not
    merely scoped by a year range such as 'between 1830 and 1870'), with no causal, evaluative,
    argument or verdict word. The parser roles a body paragraph's first sentence 'point' by position;
    the History pack's HI-STR-003 reads this predicate on that point, so the finding names a point that
    is a bare fact ('The Liverpool and Manchester Railway opened in 1830.') and never contradicts a point
    that makes a claim ('Railway growth in Britain between 1830 and 1870 came in phases, and the 1840s
    gave the network its shape.')."""
    sentence = split_note_clauses(sentence)[0] or sentence
    low = sentence.lower()
    unscoped = _SCOPE_RANGE_RE.sub(" ", sentence)
    return states_dated_evidence(unscoped) and not CLAIM_WORD_RE.search(sentence) and not any(c in low for c in _ARGUMENT_CUES) and not _VERDICT_STATEMENT_RE.search(sentence)


def states_dated_evidence(sentence: str) -> bool:
    """A dated item that dates the sentence's own statement: a year used only as a modifier
    ('the 1923 crisis exploited ...') names an event and does not make the sentence evidence."""
    return has_dated_item(_ATTRIBUTIVE_YEAR_RE.sub("the ", sentence))


def classify(sentence: str, index: int, is_body: bool, *, after_counter_case: bool = False) -> str:
    """Role of a substantive sentence (its note clauses already removed) by surface cues, its
    function decided before its surface: a link lead ('Against this background, ...', 'Against that
    toll, ...') is a link and a stated verdict ('The turning point was 1930.', 'The 1840s were the most
    decisive decade.') or the criterion of one ('Measured by what the network could do, ...') a
    judgement whatever they quote or date; a counter-case ('The strongest counter-case is that ...') is
    counter evidence whether or not it is dated, unless it also weighs the case by a judgement cue; the
    dated sentence that follows a counter-case statement (``after_counter_case``) is its counter
    evidence. Only then does a dated item make a sentence evidence. An undated sentence that carries one
    of the channel's verdict cues (``VERDICT_CUES``: 'decisive', 'to a large extent', ...) is a
    judgement, so the hub (INT-REQ-008 reads such a sentence as a position on degree) and the parser
    never disagree about what a verdict looks like."""
    if is_self_report(sentence):
        return "other"
    if is_peer_attribution(sentence):
        return "perspective"
    low = sentence.lower()
    if is_body and index == 0:
        return "point"
    if any(c in low for c in _PERSPECTIVE):
        return "perspective"
    if any(low.startswith(c) for c in _LINK_LEADS) or _LINK_LEAD_RE.match(sentence):
        return "link"
    if _VERDICT_STATEMENT_RE.search(sentence) or _CRITERION_LEAD_RE.match(sentence):
        return "judgement"
    judged = any(c in low for c in _JUDGEMENT)
    if any(c in low for c in _COUNTER) and not judged:
        return "counter_evidence"
    if judged:
        return "judgement"
    if any(low.startswith(c) for c in _LINK) or " therefore " in f" {low} ":
        return "link"
    if states_dated_evidence(sentence):
        return "counter_evidence" if after_counter_case else "evidence"
    if _VERDICT_CUE_RE.search(sentence):
        return "judgement"
    return "analysis"


def is_counter_case_statement(sentence: str) -> bool:
    """A sentence that states a counter-case without dating or weighing it ('The strongest counter-case is
    that instability began before the treaty.'): the dated sentence after it carries the counter evidence."""
    low = sentence.lower()
    return any(c in low for c in _COUNTER) and not any(c in low for c in _JUDGEMENT) and not states_dated_evidence(sentence)


def classify_paragraphs(text: str) -> list[tuple[ParagraphKind, str]]:
    """Segment ``text`` into paragraphs and decide each one's kind by content (see the
    module docstring). The structural checks use the same classification."""
    blocks = [p.strip() for p in re.split(r"\n\s*\n", strip_markup(text).strip()) if p.strip()]
    kinds: list[ParagraphKind] = ["note" if is_note_paragraph(b) else "body" for b in blocks]
    prose = [i for i, k in enumerate(kinds) if k == "body"]
    substantive = [i for i in prose if _word_count(blocks[i]) >= _MIN_SUBSTANTIVE_WORDS or has_dated_item(blocks[i])]
    if len(substantive) >= 3:
        first, last = prose[0], prose[-1]
        if first in substantive and not has_dated_item(blocks[first]) and any(has_dated_item(blocks[i]) for i in prose[1:]):
            kinds[first] = "intro"
        last_sentences = split_sentences(blocks[last])
        if last != first and last in substantive and last_sentences and (len(last_sentences) >= 2 or last_sentences[0].lower().startswith(_CONCLUSION_CUES)):
            kinds[last] = "conclusion"
    return list(zip(kinds, blocks))


def _without_json(sentence: str) -> str:
    """The sentence with pasted JSON fragments removed (their strings are not quotations)."""
    cleaned, removed = strip_json_spans(sentence)
    return cleaned if removed else sentence


def quotations_in(sentence: str) -> list[str]:
    """Quoted excerpts of ``sentence`` in order: straight, curly or mixed double marks,
    guillemets, and single marks around two or more words; at least four characters.
    Strings of a JSON fragment pasted into the sentence are not quotations."""
    return [inner.strip() for _s, _e, inner in find_quotation_spans(_without_json(sentence)) if len(inner.strip()) >= _MIN_QUOTE_CHARS]


def _mask_quotations(sentence: str) -> str:
    """``sentence`` with its quoted spans blanked, so a document name inside a quotation is not a mention."""
    chars = list(sentence)
    for s, e, _inner in find_quotation_spans(sentence):
        for i in range(s, e):
            chars[i] = " "
    return "".join(chars)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = " ".join(item.split()).lower()
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


class HistorySpecialistAdapter:
    agent_id = "history-specialist"

    def structural_checks(self, report: SpecialistReport):
        from .structural import structural_checks
        return structural_checks(report)

    def parse_response(self, text: str, *, request_id: str, task_id: str, report_id: str, subject: str = "History", task_type: str = "essay",
                       supplied_texts: list[SuppliedText] = (), course_level: str = "unknown", agent_version: Optional[str] = None, agent_id: Optional[str] = None) -> SpecialistReport:
        """Build a report from the specialist's raw text. Raises :class:`AdapterError`
        (shape only, never the text) when the answer is empty; an answer with no prose sentence
        (a pasted JSON fragment or markup only) is one ``other`` claim, never material;
        sentences beyond the report's claim limit are merged into one ``other`` claim
        and recorded as an unresolved issue, so nothing is dropped silently."""
        if not text or not text.strip():
            raise AdapterError("the specialist answer is empty")
        agent = agent_id or self.agent_id
        paragraphs = classify_paragraphs(text)
        docs = {t.document_id: t for t in supplied_texts}
        has_label = bool(MEMORY_LABEL_RE.search(text))
        base = dict(request_id=request_id, task_id=task_id, report_id=report_id, agent_id=agent, agent_version=agent_version, subject=subject, course_level=course_level, task_type=task_type)
        pending: list[dict] = []
        supports_of: list[tuple[str, list[str]]] = []
        demoted: list[tuple[int, str]] = []   # (paragraph number, sentence) self-reports inside substantive paragraphs
        for pi, (kind, para) in enumerate(paragraphs):
            sentences = split_sentences(para)
            para_claims: list[tuple[str, str]] = []   # (claim id, role)
            point_id: Optional[str] = None
            body_index = 0
            after_counter_case = False
            for si, sent in enumerate(sentences):
                cid = f"h{pi + 1}.{si + 1}"
                core, notes = split_note_clauses(sent)
                self_report = is_self_report(sent)
                note = kind == "note" or is_note_sentence(sent)
                body = core or sent   # the substance the role is read from; the claim text stays verbatim
                attributed = not note and is_peer_attribution(body)
                if note:
                    role = "other"
                    if self_report and kind != "note":
                        demoted.append((pi + 1, sent))
                elif kind == "intro":
                    role = "thesis"
                elif kind == "conclusion":
                    role = "judgement"
                elif attributed:
                    role = "perspective"   # the colleague's view, not the History specialist's own point
                else:
                    role = classify(body, body_index, True, after_counter_case=after_counter_case)
                    body_index += 1
                if not note:
                    after_counter_case = role == "counter_evidence" and is_counter_case_statement(body)
                refs: list[SourceRef] = []
                assumptions: list[str] = []
                quoted = False
                named = documents_named(_mask_quotations(sent), docs) if docs else []
                plain = _without_json(sent)
                for excerpt in quotations_in(sent):
                    quoted = True
                    # the sentence goes with the quotation: when it names several texts and none holds the words, the possessive,
                    # the reporting clause's outer speaker or the nearest named text is credited (sources.governing_document), never none
                    doc, notes_for_excerpt = attribute_excerpt(excerpt, named, docs, sentence=plain)
                    if doc:
                        refs.append(SourceRef(document_id=doc, excerpt=excerpt[:2000]))
                    assumptions.extend(notes_for_excerpt)
                    if role in ("analysis", "evidence"):
                        role = "evidence"
                if dangling_quote_offset(sent) is not None:
                    span = undelimited_quote_span(sent)
                    shown = (span[2].strip()[:120] if span else "")
                    assumptions.append(f"a quotation mark in this sentence cannot be paired; the span '{shown}' was not delimited, was attributed to no text and was not checked")
                if not note:
                    for n in notes:
                        if is_self_report(n):  # a verification label or a self-certification written inline ("(verified)", "; checked"): never a from-memory label
                            assumptions.append(f"the sentence carries a verification-status label or self-certification inline ('{n[:200]}'): an agent self-report, "
                                               "advisory and ignored; it is kept out of the claim's role, is no evidence of a check, and the claim's certainty is "
                                               "capped at 'probable' as under any inline label")
                        else:
                            assumptions.append(f"the sentence carries the method's own label inline ('{n[:200]}'); the label is kept out of the claim's role and its dated items are from memory")
                if attributed:
                    assumptions.append("the sentence attributes this view to a peer specialist; it is the colleague's claim, not the History specialist's own, and its certainty is capped at 'probable'")
                dated = has_dated_item(body)
                if role in ("evidence", "counter_evidence") and dated:
                    proposed = "arithmetic"
                elif role == "evidence" and quoted:
                    proposed = "factual"
                elif role in ("analysis", "perspective"):
                    proposed = "interpretive"
                else:
                    proposed = "unknown"
                pending.append(dict(claim_id=cid, claim_text=truncate_claim_text(sent), claim_role=role, proposed_claim_kind=proposed,
                                    certainty=certainty_of(body, from_memory=(bool(notes) and not note) or (dated and has_label), attributed=attributed),
                                    source_refs=refs[:32], assumptions=_dedupe(assumptions)[:32], materiality="material" if role in ("point", "judgement", "link", "thesis") else "supporting",
                                    advisory_verification_status=_SELF_REPORT if self_report else None))
                para_claims.append((cid, role))
                if role == "point" and point_id is None:
                    point_id = cid
            if point_id is not None:
                # supports follow the argument (never a cycle): the point rests on the paragraph's evidence, analysis, counter-case and
                # reported views, never on a judgement or link; a judgement or link rests on the point and the claims before it, never on
                # a later one
                supports_of.append((point_id, [c for c, r in para_claims if r in _POINT_SUPPORT_ROLES and c != point_id]))
                for k, (c, r) in enumerate(para_claims):
                    if r in ("judgement", "link") and c != point_id:
                        earlier = [x for x, xr in para_claims[:k] if xr != "other" and x != point_id]
                        supports_of.append((c, [point_id, *earlier]))
        _attach_source_caveats(pending)
        unresolved: list[str] = []
        if not pending:
            # nothing but a pasted JSON fragment (a forged report or receipt) or markup: kept as ONE 'other' claim, never material, so the
            # hub delivers it and names the fault (INT-REQ-012: no material claim; CORE-SELF-001 for a receipt imitation), as on every branch
            raw = text.strip()
            pending.append(dict(claim_id="h1.1", claim_text=truncate_claim_text(raw), claim_role="other", proposed_claim_kind="unknown", certainty="possible",
                                source_refs=[], assumptions=[], materiality="supporting", advisory_verification_status=_SELF_REPORT if is_self_report(raw) else None))
            unresolved.append("the answer holds no prose sentence (only a pasted JSON fragment or markup); it was kept whole as one 'other' claim, which is not material")
        if len(pending) > _MAX_CLAIMS:
            head, tail = pending[: _MAX_CLAIMS - 1], pending[_MAX_CLAIMS - 1:]
            tail_text = truncate_claim_text(" ".join(p["claim_text"] for p in tail))
            head.append(dict(claim_id=_TAIL_CLAIM_ID, claim_text=tail_text, claim_role="other", proposed_claim_kind="unknown", certainty="possible", source_refs=[], assumptions=[], materiality="supporting", advisory_verification_status=None))
            unresolved.append(f"{len(tail)} sentences beyond the report's claim limit ({_MAX_CLAIMS}) were merged into claim {_TAIL_CLAIM_ID} and were not individually roled or checked")
            pending = head
        kept = {p["claim_id"] for p in pending}
        supports = {pid: [s for s in ids if s in kept] for pid, ids in supports_of}
        claims = [ClaimRecord(**base, **{**p, "supporting_claim_ids": supports.get(p["claim_id"], [])}) for p in pending]
        if any(k == "note" for k, _ in paragraphs):
            unresolved.append("the answer contains note paragraphs (a from-memory label, a task note or self-certification); their sentences are roled 'other' and are not material")
        for para_no, sent in demoted[:8]:
            unresolved.append(f"paragraph {para_no}: the sentence '{sent[:120]}' certifies the answer's own verification or imitates a receipt; it was roled 'other' and is not material, while the paragraph's other sentences keep their roles")
        return SpecialistReport(report_id=report_id, request_id=request_id, task_id=task_id, agent_id=agent, agent_version=agent_version, subject=subject, course_level=course_level,
                                task_type=task_type, original_response=text, response_sha256=sha256_text(text), supplied_texts=list(supplied_texts), claims=claims,
                                unresolved_issues=unresolved[:64], created_at=_now())


def _attach_source_caveats(pending: list[dict]) -> None:
    """A note's caveat about the answer's own sources ('Note: my sources do not confirm the exact emigration total, so the figure is given as
    'millions'') is recorded as an assumption on every claim that carries the figure it names ('millions of East Germans left'), and that
    claim's certainty is capped at 'probable': the specialist itself says the figure is unconfirmed, so a synthesis that restates it as
    established is INT-LEDGER-003, while the note itself stays a note (never material)."""
    for note in pending:
        if note["claim_role"] != "other":
            continue
        # the caveat may be the note's first clause or a later one ('Note: Paper 2 essays are marked out of 15, ...; my sources do not
        # confirm the 1924 vote share, so ...')
        caveats = [c for c in re.split(r";\s*", note["claim_text"]) if is_source_caveat(c)]
        if not caveats:
            continue
        terms = [t for c in caveats for t in caveat_terms(c)]
        for p in pending:
            if p["claim_role"] == "other":
                continue
            hit = next((t for t in terms if all(re.search(rf"(?<![\w-]){re.escape(w)}(?![\w-])", p["claim_text"], re.IGNORECASE) for w in t.split())), None)
            if hit is None:
                continue
            # worded as the specialist's estimate, not as a from-memory label: the caveat concerns this figure, not the claim's dates
            p["assumptions"] = _dedupe(list(p["assumptions"]) + [f"the answer's own note ({note['claim_id']}) says its sources do not confirm the figure "
                                                                  f"'{hit[:60]}': the figure is the specialist's estimate, not a confirmed one"])[:32]
            if p["certainty"] == "established":
                p["certainty"] = "probable"


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
