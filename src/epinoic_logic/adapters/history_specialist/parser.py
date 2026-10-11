"""Heuristic parser for History specialist responses written with the pack's core
operation: Claim -> Evidence -> Analysis -> Judgement -> Link (Response application §3,
Structures §5). Sentences are assigned roles from surface cues; the point of each body
paragraph is wired to every other argument claim in that paragraph, and each judgement
or link claim is wired to the point and the paragraph's other argument claims, so the
paragraph's verdict is an argument the translator can formalize. Heuristic by design:
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
a link lead ('Against this background, ...') is a ``link`` and a stated verdict ('The turning
point was 1930.') a ``judgement``, both material whatever they date or quote; a counter-case
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
from ..markdown import (MEMORY_LABEL_RE, dangling_quote_offset, find_quotation_spans, is_memory_label, is_self_certification, split_list_items,  # noqa: F401
                        split_note_clauses, strip_markup, truncate_claim_text, undelimited_quote_span)
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
#: A sentence that states the verdict a request asks for ('The turning point was 1930.', 'X mattered most'): a judgement, dated or not.
_VERDICT_STATEMENT_RE = re.compile(
    r"\b(?:the|a)\s+(?:real\s+|true\s+|decisive\s+|key\s+|critical\s+|crucial\s+|main\s+)?turning[- ]point\s+(?:was|came|is|lay|fell)\b"
    r"|\b(?:was|is|marked|became|proved)\s+(?:the|a)\s+(?:real\s+|true\s+|decisive\s+|key\s+|critical\s+|crucial\s+|main\s+)?turning[- ]point\b"
    r"|\bthe\s+(?:decisive|pivotal|critical|crucial)\s+(?:year|moment|month|factor|cause|event|turning point|break)\s+(?:was|is|came)\b"
    r"|\b(?:was|is|proved|became)\s+the\s+(?:decisive|pivotal|critical|crucial)\s+(?:year|moment|month|factor|cause|event|break)\b"
    r"|\bthe\s+most\s+(?:important|significant|decisive)\s+(?:year|cause|factor|event|reason|moment|effect|consequence)\s+(?:was|is)\b"
    r"|\b(?:was|is)\s+the\s+most\s+(?:important|significant|decisive)\b"
    r"|\b(?:the\s+)?watershed\s+(?:was|came)\b|\b(?:was|is|marked)\s+(?:the|a)\s+watershed\b"
    r"|\b(?:mattered|matters)\s+most\b",
    re.IGNORECASE)
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
    r"phrase|phrasing|claim|point|paragraph|reading|account|words?|view|argument|analysis|verdict|conclusion)\b",
    re.IGNORECASE,
)
_ESTABLISHED = ("shows", "establishes", "demonstrates", "made", "led to", "was decisive", "proves", "was responsible")
_PROBABLE = ("suggests", "indicates", "is consistent with", "points to", "arguably")
_POSSIBLE = ("can be read as", "may have", "some historians argue", "it is possible that", "perhaps")
_MIN_SUBSTANTIVE_WORDS = 25   # a paragraph this short (and undated) does not make the answer multi-paragraph
_MAX_ASIDE_WORDS = 12         # a one-sentence undated line without an argument cue is an aside, not a claim
_MIN_QUOTE_CHARS = 4
_MAX_CLAIMS = 512
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
    """A sentence that is nothing but a label about the text: a self-report, or a sentence
    whose substance is empty once its from-memory / task-note clauses are removed. A
    substantive sentence with an inline label is NOT a note (see :func:`split_note_clauses`)."""
    if is_self_report(sentence):
        return True
    core, _notes = split_note_clauses(sentence)
    return not core


def is_peer_attribution(sentence: str) -> bool:
    """True when the sentence's subject is a peer specialist's view ('The English specialist
    argues that ...'); a sentence that merely cites the peer mid-way ('..., bearing out the
    English specialist's claim that ...') is the History specialist's own."""
    return bool(_PEER_ATTRIBUTION_RE.match(sentence.strip()))


def is_note_paragraph(paragraph: str) -> bool:
    """All sentences are labels (from-memory disclaimers, task notes, self-reports, JSON
    fragments), or the paragraph is a short undated aside with no argument cue. One
    self-report inside a substantive paragraph does NOT make the paragraph a note: only
    that sentence is demoted (see ``parse_response``)."""
    sentences = split_sentences(paragraph)
    if not sentences:
        return False
    if all(is_note_sentence(s) for s in sentences):
        return True
    low = paragraph.lower()
    return len(sentences) == 1 and _word_count(paragraph) < _MAX_ASIDE_WORDS and not has_dated_item(paragraph) and not any(c in low for c in _ARGUMENT_CUES)


def certainty_of(sentence: str, *, from_memory: bool = False, attributed: bool = False) -> str:
    """Agent-stated certainty from hedging cues; a dated claim made under a from-memory
    label (``from_memory``) or a view attributed to a peer (``attributed``) is capped at
    ``probable``, since the specialist itself says the item is unverified recollection or
    a colleague's reading."""
    low = sentence.lower()
    if any(c in low for c in _POSSIBLE):
        level = "possible"
    elif any(c in low for c in _PROBABLE):
        level = "probable"
    else:
        level = "established"
    if (from_memory or attributed) and level == "established":
        level = "probable"
    return level


#: Causal or evaluative words that make a sentence a claim rather than a bare dated fact ('a major but partial cause of ...').
CLAIM_WORD_RE = re.compile(
    r"\b(?:responsible|because|caused?|causes|causing|led|leads?|made|makes?|turned|created|decisive|major|minor|partial|partly|significant|important|mainly|primarily|"
    r"chiefly|largely|extent|degree|therefore|thus|explains?|shows?|reveals?|mattered|matters|crucial|central|key|chief|principal|considerable|limited|ultimately|"
    r"undermined|weakened|strengthened|enabled|allowed|forced|ensured|meant|reason|consequence|result(?:ed)?|effect|impact|transformed|precondition)\b", re.IGNORECASE)
def opens_with_fact(sentence: str) -> bool:
    """A sentence that states only a dated fact: dated (not merely naming 'the 1923 crisis'), with no causal,
    evaluative, argument or verdict word. The parser roles a body paragraph's first sentence 'point' by
    position; the History pack's HI-STR-003 reads this predicate on that point, so the finding names a
    point that is a bare fact and never contradicts a point that makes a claim."""
    sentence = split_note_clauses(sentence)[0] or sentence
    low = sentence.lower()
    return states_dated_evidence(sentence) and not CLAIM_WORD_RE.search(sentence) and not any(c in low for c in _ARGUMENT_CUES) and not _VERDICT_STATEMENT_RE.search(sentence)


def states_dated_evidence(sentence: str) -> bool:
    """A dated item that dates the sentence's own statement: a year used only as a modifier
    ('the 1923 crisis exploited ...') names an event and does not make the sentence evidence."""
    return has_dated_item(_ATTRIBUTIVE_YEAR_RE.sub("the ", sentence))


def classify(sentence: str, index: int, is_body: bool, *, after_counter_case: bool = False) -> str:
    """Role of a substantive sentence (its note clauses already removed) by surface cues, its
    function decided before its surface: a link lead ('Against this background, ...') is a link
    and a stated verdict ('The turning point was 1930.') a judgement whatever they quote or date;
    a counter-case ('The strongest counter-case is that ...') is counter evidence whether or not it
    is dated, unless it also weighs the case by a judgement cue; the dated sentence that follows
    a counter-case statement (``after_counter_case``) is its counter evidence. Only then does a
    dated item make a sentence evidence."""
    if is_self_report(sentence):
        return "other"
    if is_peer_attribution(sentence):
        return "perspective"
    low = sentence.lower()
    if is_body and index == 0:
        return "point"
    if any(c in low for c in _PERSPECTIVE):
        return "perspective"
    if any(low.startswith(c) for c in _LINK_LEADS):
        return "link"
    if _VERDICT_STATEMENT_RE.search(sentence):
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
    if any(c in low for c in _ANALYSIS):
        return "analysis"
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
        (shape only, never the text) when the answer is empty or yields no sentences;
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
                for excerpt in quotations_in(sent):
                    quoted = True
                    doc, notes_for_excerpt = attribute_excerpt(excerpt, named, docs)
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
                                    certainty=certainty_of(body, from_memory=dated and (has_label or bool(notes)), attributed=attributed),
                                    source_refs=refs[:32], assumptions=_dedupe(assumptions)[:32], materiality="material" if role in ("point", "judgement", "link", "thesis") else "supporting",
                                    advisory_verification_status=_SELF_REPORT if self_report else None))
                para_claims.append((cid, role))
                if role == "point" and point_id is None:
                    point_id = cid
            if point_id is not None:
                argument = [c for c, r in para_claims if r != "other"]   # notes are not supports
                supports_of.append((point_id, [c for c in argument if c != point_id]))
                for c, r in para_claims:
                    if r in ("judgement", "link") and c != point_id:
                        supports_of.append((c, [x for x in argument if x != c]))   # the point comes first: it is the first argument claim
        if not pending:
            raise AdapterError("the specialist answer yields no sentences")
        unresolved: list[str] = []
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


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
