"""Claim and report rules of the argument family (rules ``argdiag-2``).

``RULES`` are claim-layer rules: each is a callable ``rule(ctx: diag_core.DiagContext) -> Iterable[NamedDiagnostic]``
(the code table's claim-layer argument codes, ``ARG-EQ-001`` and the claim form of ``ARG-CIRC-001``). ``REPORT_RULES``
are report-layer rules: ``rule(rctx: diag_core.ReportContext) -> Iterable[NamedDiagnostic]`` (``ARG-BARE-001``), run
once per delivered report, with no outcome needed.

Every rule is guarded by :mod:`.diag_core`: one that raises is named in the outcome's ``diagnosis_incomplete`` and fires
nothing, and the caps (an ambiguous translation, a task that is not source-bound) and the suppression of dominated
warnings are applied there, so a rule only names what it finds, with ``named.named_diagnostic``. Rules read the
validated problem, the grounding records, the claim structure and texts as strings (through :mod:`epinoic_logic.lexis`);
nothing is evaluated.

The rules:

* **ARG-EQ-001** (claim, warning, never capped: the ambiguity is the defect). The translation's ambiguity flags include
  one whose code is ``EQUIVOCATION``, ``SENSE_SPLIT`` or ``TWO_SENSES`` (case and separators ignored): the translator
  read one word of the claim in two senses, and the point holds only if they are taken as one. The flag's message is cut
  to 160 characters and quoted in the diagnostic. A flag of any other code names nothing here.
* **ARG-CIRC-001** (claim form, warning). The translation was refused as circular: its status is
  INVALID_FORMALIZATION and the last attempt was rejected by the pipeline's circularity rule (the engine's ``E112``
  test, applied before any engine run). The restating premises and the kinds their groundings claim are read back from
  the pipeline's own diagnostic, which names them; nothing the provider wrote decides it, since the rejection text is the
  pipeline's and its prefix must match exactly. When every restating premise is a fact the claim states from subject
  knowledge (``general_knowledge``) and the claim's own text offers no reason for it, the claim is a bare factual
  sentence that the encoding restated: the record is info (no verdict, no accusation). A restatement by the writer's own
  step, an assumption or a source or task label no check established is the warning.
* **ARG-BARE-001** (report, warning). A delivered claim is a bare assertion when all of these hold: a request item's
  command term asks for reasons (explain, evaluate, discuss, justify, to what extent, analyse or analyze, examine,
  assess, why, recommend), or its words ask for them ("with reasons", "giving reasons", "give a reason", "with
  justification", ...); the claim is material, is a point, judgement or other argued role (not evidence, a quantitative claim,
  a source description or a structural line), and no claim cites it as support; it has no supporting claims and its own
  text, quotations masked, has no reason connective ("because" but not "because of", "since", "so", "therefore", "thus",
  "hence", "given that", "which shows", "as ... shows", "as shown by", ...); and no other claim of its answer section
  (the paragraph of the answer it stands in, or the whole answer when it has one paragraph) has a supporting role, a
  reason connective or supporting claims. It needs no outcome, so it reaches a claim that was never translated. When the
  report holds no material claim at all (a text parser that found no point marks a lone sentence "supporting"), a claim
  of an argued role other than a note counts as the answer's assertion: the answer then asserts it and nothing else. A
  non-material claim keeps its severity and gets no receipt finding (the channel's materiality rule). A claim that is one
  quotation wrapping two or more sentences (a quoted passage, or the writer's own sentences wrapped in marks: '"The crash
  of 1929 came after a speculative boom. Banks failed in 1930 and 1931."') is no bare assertion: the parsers keep such a
  quotation as one claim, so its later sentences, which the same words unwrapped give as supporting claims, are inside
  it, and the rule cannot tell its judgement from its reasons there (repair round 1, re-run review rc-7). One quoted
  sentence is read as the same sentence unquoted is. A claim whose own text quotes a supplied text (three words or more,
  located there by the grounding reader) carries its evidence in the same sentence and is no bare assertion (repair round
  2); an invented quotation supports nothing. A claim whose own clause gives its reason by a cause phrase ("because of",
  "due to", "as a result of", "thanks to", "following" an event, "by" a means: :data:`CAUSE_PHRASES`), with the claim's
  own words before the phrase and an event or means of at least three content words after it, offers a cause and is no
  bare assertion (:func:`offers_cause`, accuracy round 1, DIFF3-01: "The Weimar government faced hyperinflation in 1923
  because of the money it printed ..." was named one); a bare "because of the war" names no event and is still read.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Callable, Iterable, Optional, Sequence

from .. import lexis
from ..engine import argument_cues as _CUES
from ..named import EvidenceSpan, NamedDiagnostic, model_text, named_diagnostic
from .contracts import ClaimRecord, SpecialistReport, TranslationStatus

__all__ = ["RULES", "REPORT_RULES", "EQUIVOCATION_FLAG_CODES", "REASON_TERMS", "REASON_CONNECTIVES", "SUPPORTING_ROLES", "ASSERTION_ROLES",
           "equivocation_flag", "circular_refusal", "bare_assertion", "answer_sections", "has_reason_connective", "mask_quotations",
           "wrapped_passage"]

#: Ambiguity-flag codes that say one word was read in two senses (compared case-insensitively, "-" and " " read as "_").
EQUIVOCATION_FLAG_CODES: frozenset[str] = frozenset({"equivocation", "sense_split", "two_senses"})
#: Command terms that ask for reasons (ARG-BARE-001), matched in an item's command term or its words.
REASON_TERMS = lexis.cue_table(("explain", "evaluate", "discuss", "justify", "to what extent", "analyse", "analyze", "examine", "assess", "why",
                                 # a recommendation is a course of action with its supporting reasons (the command term), and a request
                                 # may ask for the reasons in words (repair round 2, holdout2 bare-assertion class)
                                 "recommend", "with reasons", "giving reasons", "give reasons", "give a reason", "with justification",
                                 "justifying", "with reference to reasons"))
#: Reason connectives (the engine's table, ``engine.argument_cues.REASON_CONNECTIVES``). "because" counts only when "of"
#: does not follow it (a cause phrase, not a reason clause).
REASON_CONNECTIVES = _CUES.REASON_CONNECTIVES
#: Roles of a claim that supports a point within its section (ARG-BARE-001 iv).
SUPPORTING_ROLES: frozenset[str] = frozenset({"evidence", "counter_evidence", "quantitative", "analysis", "link", "device", "interpretation", "effect",
                                              "origin", "purpose", "content", "value", "limitation"})
#: Roles of a claim that can be a bare assertion (ARG-BARE-001 ii).
ASSERTION_ROLES: frozenset[str] = frozenset({"thesis", "point", "judgement", "analysis", "interpretation", "effect", "value", "limitation",
                                             "perspective", "link", "other"})
_FLAG_CHARS = 160
#: The pipeline's own circularity rejection: "attempt <n>: E112: circular: premise(s) <id> (<kind>), ... restate ...".
_ITEM = r"[A-Za-z][A-Za-z0-9_.:-]{0,127}(?: \([a-z_]{1,40}\))?"
_CIRCULAR_RE = re.compile(rf"attempt (\d{{1,3}}): E112: circular: premise\(s\) ({_ITEM}(?:, {_ITEM}){{0,7}}) restate ")
_ITEM_RE = re.compile(r"([A-Za-z][A-Za-z0-9_.:-]{0,127})(?: \(([a-z_]{1,40})\))?")
#: The grounding kind of a fact the writer states from subject knowledge (``engine.argument_cues.KNOWLEDGE_KIND``).
_KNOWLEDGE_KIND = _CUES.KNOWLEDGE_KIND
#: The kinds by which a premise claims that the task itself states it (a restatement of the task offers no argument).
_TASK_STATEMENT_KINDS = frozenset({"task_setting", "rubric_rule"})
#: Words a heading uses to name the task rather than to say anything ("Task:", "Guiding question:").
_TASK_NAMING_WORDS = frozenset({"task", "tasks", "question", "questions", "guiding", "prompt", "title", "heading"})


def _restates_task_words(claim_text: str, task_text: Optional[str]) -> bool:
    """Whether a claim only restates the task: it is a question (it asserts nothing: "Task — Paper 1, SL — How does the
    writer present ...?"), or it is made only of the task record's own words (two or more content words, none of them a
    word the task does not hold, the words that name the task aside). Bounded; read as data."""
    if not claim_text:
        return False
    if claim_text.strip().endswith("?"):
        return True
    if not task_text:
        return False
    wanted = {lexis.root(t) for t in lexis.tokens(claim_text[:2000]) if t not in lexis.FUNCTION_WORDS and t not in _TASK_NAMING_WORDS}
    held = {lexis.root(t) for t in lexis.tokens(task_text[:20000])}
    return len(wanted) >= 2 and wanted <= held
_ATTEMPT_RE = re.compile(r"attempt (\d{1,3}): ")
_QUOTES = {'"': '"', "“": "”", "‘": "’", "«": "»"}
_MAX_QUOTE = 600
#: the marks that can wrap a whole claim (the straight single quote too: a wrapped answer, never a quotation masked in prose)
_WRAPS = {**_QUOTES, "'": "'"}
#: a sentence boundary inside a wrapped claim: an end mark, an optional closing mark, space, and a capital, a digit or a mark
_INNER_BOUNDARY_RE = re.compile(r"[.!?][\"'”’»)]?\s+[A-Z0-9“\"‘'«(]")


def _flag_code(code: str) -> str:
    return code.strip().casefold().replace("-", "_").replace(" ", "_")


def equivocation_flag(ctx) -> list[NamedDiagnostic]:
    """ARG-EQ-001: the translation flagged one word read in two senses."""
    interp = ctx.translation.interpretation
    if interp is None:
        return []
    for flag in interp.ambiguity_flags:
        if _flag_code(flag.code) not in EQUIVOCATION_FLAG_CODES:
            continue
        said = model_text(flag.message, _FLAG_CHARS)
        return [named_diagnostic("ARG-EQ-001", claim_ids=[ctx.claim.claim_id], derivation="ir_structure",
                                 evidence=[EvidenceSpan(source_kind="claim", source_id=ctx.claim.claim_id[:200], text=ctx.claim.claim_text[:300])],
                                 message=(f"equivocation: the translation flagged one word read in two senses ({flag.code[:40]}: {said!r}); the point "
                                          "holds only if the two senses are taken as one, so the argument rests on that equivocation"))]
    return []


def circular_refusal(ctx) -> list[NamedDiagnostic]:
    """ARG-CIRC-001 (claim form): the pipeline refused the translation as circular on its last attempt."""
    tr = ctx.translation
    if tr.status is not TranslationStatus.INVALID_FORMALIZATION:
        return []
    attempts = [int(m.group(1)) for d in tr.diagnostics if (m := _ATTEMPT_RE.match(d))]
    if not attempts:
        return []
    last = max(attempts)
    for d in tr.diagnostics:
        m = _CIRCULAR_RE.match(d)
        if m is None or int(m.group(1)) != last:
            continue
        items = [_ITEM_RE.fullmatch(x) for x in m.group(2).split(", ")]
        ids = [x.group(1) for x in items if x is not None]
        kinds = [x.group(2) for x in items if x is not None]
        evidence = [EvidenceSpan(source_kind="claim", source_id=ctx.claim.claim_id[:200], text=ctx.claim.claim_text[:300])]
        if kinds and all(k == _KNOWLEDGE_KIND for k in kinds) and not has_reason_connective(ctx.claim.claim_text):
            return [named_diagnostic("ARG-CIRC-001", severity="info", layer="claim", claim_ids=[ctx.claim.claim_id], assertion_ids=ids,
                                     derivation="ir_structure", evidence=evidence,
                                     message=(f"the translation was refused because its premise(s) {', '.join(ids)} restate the point; each is a fact "
                                              "the claim states from subject knowledge, and the claim offers no reason for it, so the restatement is "
                                              "the encoding's, not a circle shown in the claim: no verdict either way"))]
        # the encoding grounds its point too on the task: beyond the restating premises, its grounded items (the point and its
        # symbols) all claim the task's authority (a refused translation keeps its grounding checks, not its problem)
        others = [c for c in tr.grounding_checks if c.target_id not in ids]
        on_task = bool(others) and all(c.kind in _TASK_STATEMENT_KINDS for c in tr.grounding_checks)
        if (kinds and all(k in _TASK_STATEMENT_KINDS for k in kinds) and not has_reason_connective(ctx.claim.claim_text)
                and (on_task or _restates_task_words(ctx.claim.claim_text, ctx.task_text))):
            # an encoding that restates the task: its point too is grounded on the task (a report's heading "Task — Paper 1,
            # SL — How does the writer present ...?" encoded as the task's statement restating itself), or the claim only
            # restates the task (a question, which asserts nothing, or the task's own words). No argument is offered, so no
            # circle is shown in the claim (close round 1, arena r7 lit-t13). A claim that gives a reason, or a point of the
            # writer's own asserted under the task's label ("Shelley's sonnet was written in 1817." with no task saying so),
            # stays a circle at warning
            return [named_diagnostic("ARG-CIRC-001", severity="info", layer="claim", claim_ids=[ctx.claim.claim_id], assertion_ids=ids,
                                     derivation="ir_structure", evidence=evidence,
                                     message=(f"the translation was refused because its premise(s) {', '.join(ids)} restate the point; each claims the "
                                              "task's authority for what the claim states, and the claim offers no reason for it, so the restatement "
                                              "is the encoding's, not a circle shown in the claim: no verdict either way"))]
        return [named_diagnostic("ARG-CIRC-001", layer="claim", claim_ids=[ctx.claim.claim_id], assertion_ids=ids, derivation="ir_structure",
                                 evidence=evidence,
                                 message=(f"circular: the translation was refused because its premise(s) {', '.join(ids)} restate the point and no "
                                          "check in this process established them (whatever their label): the point is assumed, not derived"))]
    return []


# ----------------------------------------------------------------------------------------------- the report rule

def mask_quotations(text: str) -> str:
    """``text`` with every quoted span (double quotes, curly quotes, guillemets) blanked, so a quotation's words are never
    read as the writer's own connective. Linear; an unclosed quote is left as it is."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        close = _QUOTES.get(text[i])
        if close is None or (text[i] == "‘" and i > 0 and text[i - 1].isalpha()):
            i += 1
            continue
        j = text.find(close, i + 1, min(n, i + 1 + _MAX_QUOTE))
        if j == -1:
            i += 1
            continue
        for k in range(i + 1, j):
            out[k] = " "
        i = j + 1
    return "".join(out)


def wrapped_passage(text: str) -> bool:
    """Whether ``text`` is one quotation wrapping two or more sentences: it opens with a quotation mark and ends with its
    closing mark (an end mark may follow it), the closing mark does not occur inside, and a sentence boundary does
    (ARG-BARE-001). A straight single quote inside counts only between two letters (an apostrophe: "didn't")."""
    s = (text or "").strip()
    close = _WRAPS.get(s[:1])
    if close is None or len(s) < 4:
        return False
    body = s[:-1] if s[-1] in ".!?" and len(s) > 4 else s
    if not body.endswith(close):
        return False
    inner = body[1:-1]
    if close == "'":
        if any(ch == "'" and not (0 < k < len(inner) - 1 and inner[k - 1].isalpha() and inner[k + 1].isalpha()) for k, ch in enumerate(inner)):
            return False
    elif close in inner:
        return False
    return _INNER_BOUNDARY_RE.search(inner) is not None


def has_reason_connective(text: str) -> bool:
    """Whether ``text`` (quotations masked) holds a reason connective; "because of" is a cause phrase, not one."""
    toks = lexis.tokens(mask_quotations(text or ""))
    for i, cue in lexis.find_cues(toks, REASON_CONNECTIVES):
        if cue == ("because",) and i + 1 < len(toks) and toks[i + 1] == "of":
            continue
        return True
    return False


def _paragraphs(text: str) -> list[tuple[int, int]]:
    """``(start, end)`` of each paragraph of ``text`` (blocks separated by a blank line)."""
    spans: list[tuple[int, int]] = []
    start, i, n = 0, 0, len(text)
    while i < n:
        if text[i] == "\n":
            j = i + 1
            while j < n and text[j] in " \t\r":
                j += 1
            if j < n and text[j] == "\n":
                if text[start:i].strip():
                    spans.append((start, i))
                while j < n and text[j] in " \t\r\n":
                    j += 1
                start = i = j
                continue
        i += 1
    if text[start:].strip():
        spans.append((start, n))
    return spans


def answer_sections(report: SpecialistReport) -> dict[str, Optional[int]]:
    """``{claim id: index of its answer section}``: the paragraph of the answer its text stands in, or None when the
    answer has one paragraph or the claim's text is not found in it (such a claim belongs to every section)."""
    text = report.original_response or ""
    paras = _paragraphs(text)
    out: dict[str, Optional[int]] = {}
    for c in report.claims:
        at = text.find(c.claim_text) if len(paras) > 1 and c.claim_text else -1
        if at < 0 and len(paras) > 1 and c.claim_text:
            at = text.find(c.claim_text[:60])
        out[c.claim_id] = next((k for k, (s, e) in enumerate(paras) if s <= at < e), None) if at >= 0 else None
    return out


def _supports(c: ClaimRecord) -> list[str]:
    return [s for s in c.supporting_claim_ids if s != c.claim_id]


def _asks_for_reasons(rctx) -> Optional[str]:
    """The first request item (or, with no items, the task text) whose command term or words ask for reasons."""
    found = _reason_items(rctx)
    if found:
        return found[0]
    if not rctx.items and rctx.task_text and lexis.has_cue(rctx.task_text, REASON_TERMS):
        return rctx.task_text
    return None


def _reason_items(rctx) -> list[str]:
    """The texts of every request item whose command term or words ask for reasons."""
    out: list[str] = []
    for item in rctx.items:
        term = (item.command_term or "").casefold()
        if (term and lexis.has_cue(term, REASON_TERMS)) or lexis.has_cue(item.text, REASON_TERMS):
            out.append(item.text)
    return out


#: The label that opens a part of a request or of an answer: "(a)", "a)", "Part (b)", "(iii)", "2.".
#: (security round 1) The white space before the label read possessively: '**' and the label cannot begin with white space, so
#: the run's longest reading is the only one the rest can follow, and the same labels are read; a text opening with a long run
#: of spaces was split between two quantifiers before failing (quadratic in the run) (tests/translate/test_security_round1_conversion.py).
_PART_LABEL_RE = re.compile(r"^\s*+(?:\*\*)?+\s*+(?:part\s+)?\(?(?P<label>[a-h]|[ivx]{1,4}|\d{1,2})\)?(?:[).:]|\s)", re.IGNORECASE)


def _part_label(text: str) -> Optional[str]:
    m = _PART_LABEL_RE.match(text or "")
    if m is None:
        return None
    raw = m.group(0).strip().casefold()
    # a bare word opening a sentence ("I think", "A firm") is no label: a label is bracketed, closed by a bracket, a full
    # stop or a colon, or said with "part"
    if not (raw.startswith(("(", "part")) or raw.endswith((")", ".", ":"))):
        return None
    return m.group("label").casefold()


def _item_part(item_text: str, task_text: str) -> Optional[str]:
    """The part label of a request item: its own opening label, else the label that opens the line of the request it stands
    in ("(b) In no more than 60 words, explain one cause ...": the item is "explain one cause ...", the part (b))."""
    own = _part_label(item_text)
    if own is not None or not task_text:
        return own
    probe = item_text[:80].strip().lower()
    low = task_text.lower()
    at = low.find(probe) if probe and len(low) == len(task_text) else -1  # the item's words in any case ("Explain" for "explain")
    if at < 0:
        return None
    line_start = task_text.rfind("\n", 0, at) + 1
    return _part_label(task_text[line_start:at + 1])


def _reason_parts(rctx) -> Optional[set[str]]:
    """The part labels of the request items that ask for reasons, when every such item stands in a labelled part ("(b)
    Explain one cause ..."); None when one does not (the requirement is the whole answer's)."""
    items = _reason_items(rctx)
    labels = {_item_part(t, rctx.task_text or "") for t in items}
    return None if not items or None in labels else labels  # type: ignore[return-value]


def _section_parts(report: SpecialistReport) -> dict[str, Optional[str]]:
    """``{claim id: the part label its answer section opens with}`` (None for a section with no label, or a claim not found)."""
    text = report.original_response or ""
    paras = _paragraphs(text)
    sections = answer_sections(report)
    labels = [_part_label(text[s:e]) for s, e in paras]
    return {cid: (labels[k] if k is not None and k < len(labels) else None) for cid, k in sections.items()}


def _asserts(c: ClaimRecord, pointless: bool) -> bool:
    """Whether ``c`` can stand as the answer's assertion: a material claim of an assertion role, or, when the report holds
    no material claim at all (a parser found no point to mark), a claim of an argued role other than a note ("other")."""
    if c.claim_role not in ASSERTION_ROLES:
        return False
    return c.materiality == "material" or (pointless and c.claim_role != "other")


def _quotes_a_supplied_text(claim: ClaimRecord, report: SpecialistReport) -> bool:
    """Whether the claim's own text quotes a supplied text: a quotation of three words or more, its closing punctuation set
    aside, that the grounding reader locates in a supplied text that is no relayed agent's report. Such a quotation is the
    claim's evidence in the same sentence ('The speaker presents the king as negligent: "The king has ignored the people for
    too long."'), so the claim is no bare assertion (repair round 2, history-bare-assertion-false-alarm); an invented
    quotation, located nowhere, supports nothing."""
    from ..adapters.markdown import cited_quotation_spans
    from ..adapters.sources import strip_trailing_punctuation
    from .grounding import is_peer_document, locate_quotation
    texts = [t for t in report.supplied_texts if not is_peer_document(t)]
    if not texts:
        return False
    for _a, _b, inner in cited_quotation_spans((claim.claim_text or "")[:4000]):
        q = strip_trailing_punctuation(inner)
        if len(q.split()) >= 3 and any(locate_quotation(q, t.text, document_id=t.document_id) is not None for t in texts):
            return True
    return False


#: The words of an evaluation that names no reason (ARG-BARE-001, repair round 2): verdict and intensity words, the generic
#: nouns of a choice and of the one it is for, and the anaphors that point back at the judgement.
EMPTY_EVALUATION_WORDS: frozenset[str] = frozenset("""
this that it these those such doing so here there is are was were be being been would will should must could can
the a an for of to by in on at with and or as its their our your his her them they we you
best better right correct ideal optimal perfect good great excellent wise sensible smart superior strongest strong clear obvious
clearly undoubtedly definitely certainly obviously surely absolutely simply truly really very most only one far by
option options choice choices strategy strategies decision decisions approach approaches way ways answer answers solution solutions
course courses action plan plans idea ideas recommendation recommendations move step pick
company companies firm firms business businesses organisation organization organisations organizations brand owner owners
""".split())
#: The anaphors that open an evaluation of the judgement before it ("This is the best option", "It is clearly right").
_EVALUATION_OPENERS = ("this ", "that ", "it ", "such ", "doing so ", "this choice ", "this option ", "this strategy ", "this decision ")


def _empty_evaluation(text: Optional[str]) -> bool:
    """Whether a claim only re-evaluates the judgement before it, naming no reason: it opens with an anaphor ("This is
    undoubtedly the best option for the company") and every word of it is a verdict, intensity or generic word
    (:data:`EMPTY_EVALUATION_WORDS`). Such a claim is no support for the judgement, nor the judgement's reason (repair round
    2, holdout2 bare-assertion class)."""
    low = " ".join(mask_quotations(text or "")[:400].lower().split())
    if not low.startswith(_EVALUATION_OPENERS):
        return False
    words = lexis.tokens(low)
    return bool(words) and all(w in EMPTY_EVALUATION_WORDS for w in words)


#: Words of a judgement that ranks or grades (repair round 3, V3-H2-STEM-MISSES): "the most effective technique", "the main
#: reason", "more important than", "clearly the best".
RANKING_WORDS: frozenset[str] = frozenset("""
most least best worst main chief principal greatest biggest strongest weakest primary key crucial decisive
more less better worse greater stronger weaker
""".split())


def _ranks(text: Optional[str]) -> bool:
    """Whether a claim's own words (quotations masked) rank or grade what it judges (:data:`RANKING_WORDS`)."""
    return any(w in RANKING_WORDS for w in lexis.tokens(mask_quotations(text or "")[:2000]))


#: Cause phrases (accuracy round 1, DIFF3-01): a claim that names its cause with one of them gives its reason in its own
#: sentence ("The Weimar government faced hyperinflation in 1923 as a result of printing money to pay striking workers"),
#: though none is a reason connective ("because of" is a cause phrase, not a reason clause).
CAUSE_PHRASES = lexis.cue_table(("because of", "due to", "owing to", "as a result of", "as a consequence of", "in consequence of",
                                 "thanks to", "on account of", "caused by", "brought about by", "triggered by", "driven by",
                                 "resulting from", "the result of", "a result of", "in response to"))
#: Means and sequence words that give a reason only with content after them: "through" a deed ("through a deal with
#: Papen"), "by" a gerund ("by using his post"), "after" an event ("after Germany resumed unrestricted submarine warfare"),
#: "following" an event; "by 1929", "after the delay" and "through the year" give none.
_MEANS_WORDS = frozenset({"through", "by", "after", "following"})
#: Generic nouns that name no cause ("due to many factors", "because of several reasons").
_EMPTY_CAUSE_WORDS = frozenset({"reason", "reasons", "factor", "factors", "cause", "causes", "thing", "things", "issue", "issues", "many",
                                "several", "various", "number", "range", "variety", "combination", "mix", "lot", "lots", "different",
                                "other", "others", "circumstance", "circumstances", "event", "events", "this", "that", "it", "these", "those"})
#: How many content words a cause phrase, or a means or sequence word, needs after it in its clause.
_MIN_CAUSE_WORDS = 2
_MIN_EVENT_WORDS = 3


def offers_cause(text: Optional[str]) -> bool:
    """Whether a claim's own text (quotations masked) names the cause of what it states (accuracy round 1, DIFF3-01): a
    cause phrase (:data:`CAUSE_PHRASES`) followed in its clause by at least two content words that are no generic noun
    (:data:`_EMPTY_CAUSE_WORDS`), "by" before a gerund ("by using his post as General Secretary"), or "through", "after"
    or "following" followed by at least three such words before the clause ends ("after Germany resumed unrestricted
    submarine warfare"). Read from the first 2,000 characters as words; linear."""
    masked = mask_quotations(text or "")[:2000]
    spans = lexis.token_spans(masked)
    toks = [w for _a, _b, w in spans]
    n = len(toks)
    # one pass each: the content words before every token, and the first token of the next clause after every token
    prefix = [0] * (n + 1)
    for k, w in enumerate(toks):
        prefix[k + 1] = prefix[k] + (0 if (w in lexis.FUNCTION_WORDS or w in _EMPTY_CAUSE_WORDS or w.isdecimal()) else 1)
    next_clause = [n] * (n + 1)
    for k in range(n - 1, 0, -1):
        breaks = any(ch in masked[spans[k - 1][1]:spans[k][0]] for ch in ",;:()—–")
        next_clause[k] = k if breaks else next_clause[k + 1]

    def content_after(j: int, need: int) -> bool:
        if j >= n:
            return False
        end = next_clause[j + 1] if j + 1 <= n else n
        return prefix[end] - prefix[j] >= need

    for i, cue in lexis.find_cues(toks, CAUSE_PHRASES):
        if content_after(i + len(cue), _MIN_CAUSE_WORDS):
            return True
    for i, w in enumerate(toks):
        if w not in _MEANS_WORDS or i + 1 >= len(toks):
            continue
        if w == "by":
            if toks[i + 1].endswith("ing") and len(toks[i + 1]) > 4 and content_after(i + 1, _MIN_CAUSE_WORDS):
                return True
        elif content_after(i + 1, _MIN_EVENT_WORDS):
            return True
    return False


#: A claim that is only a yes or no ("No.", "Yes!"): the answer to a question the text asks, never a judgement of its own.
_YES_NO_RE = re.compile(r"\W*(?:yes|no)\W*", re.IGNORECASE)


def bare_yes_no(text: Optional[str]) -> bool:
    """Whether a claim is only a yes or no (its quotations masked, at most a few characters around the word): the answer to
    a question the answer asks itself, a trace's test ("Is 38 = 67? No."), which states no judgement a request could ask
    reasons for (ARG-BARE-001; on the integrated translator the STEM and text parsers deliver such an answer as a claim of
    its own)."""
    t = mask_quotations(text or "")[:40]
    return len(t) <= 12 and _YES_NO_RE.fullmatch(t.strip()) is not None


def bare_assertion(rctx) -> list[NamedDiagnostic]:
    """ARG-BARE-001 (module docstring). A claim that only re-evaluates the judgement (:func:`_empty_evaluation`) neither
    supports it nor is supported by it: the links to and from it are set aside.

    A report that links no claim to any other gives its judgement no reason by its structure (repair round 3,
    V3-H2-STEM-MISSES): there a judgement that ranks or grades ("The opening statistic is clearly the most effective
    technique in the whole article.") beside claims that only describe ("The article opens with a statistic: ...") is a bare
    assertion: a neighbour counts as its support only through a reason connective of its own, not by its role. A text
    delivery, whose parser links the claims of a paragraph, is read as before."""
    item = _asks_for_reasons(rctx)
    if item is None:
        return []
    claims = list(rctx.report.claims)
    # the part that asks for reasons: a claim in another labelled part of the answer answers another item ("(a) Define
    # inflation." beside "(b) Explain one cause ..."), so the requirement is not its own (repair round 5, ADV5-11)
    reason_parts = _reason_parts(rctx)
    part_of = _section_parts(rctx.report) if reason_parts else {}
    empty = {c.claim_id for c in claims if _empty_evaluation(c.claim_text)}
    def supports(c: ClaimRecord) -> list[str]:
        return [] if c.claim_id in empty else [x for x in _supports(c) if x not in empty]
    cited = {s for c in claims for s in supports(c)}
    unlinked = not cited
    sections = answer_sections(rctx.report)
    pointless = not any(c.materiality == "material" for c in claims)
    out: list[NamedDiagnostic] = []
    for c in claims:
        if c.claim_id in empty:
            continue
        if reason_parts and part_of.get(c.claim_id) is not None and part_of[c.claim_id] not in reason_parts:
            continue
        if not _asserts(c, pointless) or c.claim_id in cited or supports(c) or has_reason_connective(c.claim_text) or wrapped_passage(c.claim_text):
            continue
        if offers_cause(c.claim_text):
            continue  # it names its cause in its own sentence (accuracy round 1, DIFF3-01): a reason, though no reason connective
        if bare_yes_no(c.claim_text):
            continue  # a lone "Yes." or "No." answers a question (a trace's test: "Is 38 = 67? No."): it asserts no judgement of its own
        if _quotes_a_supplied_text(c, rctx.report):
            continue
        mine = sections.get(c.claim_id)
        peers = [o for o in claims if o.claim_id != c.claim_id and o.claim_id not in empty and (mine is None or sections.get(o.claim_id) in (None, mine))]
        by_role = not (unlinked and _ranks(c.claim_text))
        if any((by_role and o.claim_role in SUPPORTING_ROLES) or supports(o) or has_reason_connective(o.claim_text) for o in peers):
            continue
        asked = model_text(item, 120)
        out.append(named_diagnostic("ARG-BARE-001", claim_ids=[c.claim_id], derivation="claim_structure",
                                    evidence=[EvidenceSpan(source_kind="claim", source_id=c.claim_id[:200], text=c.claim_text[:300])],
                                    message=(f"bare assertion: the request asks for reasons ({asked!r}), and claim {c.claim_id} states its judgement "
                                             "with no reason: no supporting claim, no reason connective, and nothing else in its answer section "
                                             "supports it")))
    return out


# ----------------------------------------------------------------------------------------------- ARG-NS-003: an unbridged leap

#: Connectives that draw the conclusion standing after them from what stands before ("A, so B"; "A. Therefore B.").
CONCLUSION_CONNECTIVES = lexis.cue_table(("so", "therefore", "thus", "hence", "consequently", "as a result", "it follows that"))
#: Connectives that give the reason standing after them for the clause they join ("B because A"; "Since A, B").
REASON_CLAUSE_CONNECTIVES = lexis.cue_table(("because", "since", "given that"))
#: Words after "since" that make it a time, not a reason ("since then", "since the war began" is read as a reason only
#: when no number or time word follows).
_SINCE_TIME_WORDS = frozenset({"then", "when", "ever", "before", "after", "the", "its", "their", "his", "her", "january", "february", "march",
                               "april", "may", "june", "july", "august", "september", "october", "november", "december", "independence"})
#: The characters that end a run of a sentence's text (:func:`_sentence_spans`).
_SENTENCE_STOPS = frozenset(".!?\n")
_SENTENCE_MARKS = frozenset(".!?")
_MAX_LEAP_TEXT = 20_000
_MAX_LEAP_SENTENCES = 400
#: The link's sides are read without what parentheses hold (an attribution, a source label, a figure).
_PAREN_RE = re.compile(r"\([^()]{0,200}\)")


#: A name in a link's side: a capitalised word that does not open the side ("the Treaty of Versailles", "Germany").
_NAME_RE = re.compile(r"(?<=[\s(\-'’])([A-Z][a-z]{2,40})\b")


def _side_roots(text: str) -> set[str]:
    from .stated_rules import meaning_roots
    return {r for r in meaning_roots(_PAREN_RE.sub(" ", text or "")) if r and not r[0].isdigit()}


def _side_names(text: str) -> set[str]:
    """The roots of the names a link's side holds (parentheses left out): what it is about, when that is a named thing."""
    return {lexis.root(m.group(1)) for m in _NAME_RE.finditer(" " + _PAREN_RE.sub(" ", text or "")[:600])}


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """The sentences of ``text`` as ``(start, end)`` spans, found in one left-to-right pass (repair round 5, ADV5-01: the
    regular expression this replaces, ``[^.!?\\n]+(?:[.!?]+(?=\\s|$)|\\n|$)`` through ``finditer``, was quadratic on a long
    run of text with no sentence end before a "." that no white space follows, such as a decimal "3.5" or "x.y"). The
    spans are exactly the old pattern's matches: a run of characters other than ".", "!", "?" and a line break, ending at
    the text's end, at a line break (kept), or at a run of ".", "!" and "?" that white space or the end follows (kept); a
    run whose marks are followed by anything else ("3.5") ends no sentence and is not a span, and reading resumes after
    those marks. At most :data:`_MAX_LEAP_SENTENCES` spans holding more than white space. Each character is read at most
    twice, so the pass is linear in the text."""
    out: list[tuple[int, int]] = []
    n = len(text)
    p = 0
    while p < n and len(out) < _MAX_LEAP_SENTENCES:
        if text[p] in _SENTENCE_STOPS:
            p += 1
            continue
        q = p
        while q < n and text[q] not in _SENTENCE_STOPS:
            q += 1
        if q >= n:
            end = n
        elif text[q] == "\n":
            end = q + 1
        else:
            r = q
            while r < n and text[r] in _SENTENCE_MARKS:
                r += 1
            if r < n and not text[r].isspace():
                p = r  # "3.5": the marks end no sentence; the old pattern matched nothing here
                continue
            end = r
        if text[p:end].strip():
            out.append((p, end))
        p = end
    return out


def _roots_of(spans: Sequence[tuple[int, int, str]]) -> set[str]:
    from .stated_rules import meaning_roots
    return meaning_roots(" ".join(w for _a, _b, w in spans))


def _capitalised_roots(text: str) -> set[str]:
    """The roots of the words ``text`` writes with a capital where a capital is a name's (not a sentence's first word)."""
    out: set[str] = set()
    for s, e in _sentence_spans(text):
        sentence = text[s:e]
        for k, (a, b, w) in enumerate(lexis.token_spans(sentence)):
            if k and sentence[a:a + 1].isupper():
                out.add(lexis.root(w))
    return out


def _states_connection(sentence: str, spans: Sequence[tuple[int, int, str]], a_roots: set[str], b_roots: set[str], names: set[str]) -> bool:
    """A sentence with no connective states the connection of a link's two sides when it holds words of both and not only
    their names: some word of either side stands in it as a plain word (in lower case, or as the sentence's first word
    when the answer and the sides never write that word as a name: ``names``). A sentence that only names the two things
    ("The Kaiser was Germany's emperor", "The King visited Germany in 1913", "Britain was worried about the Kaiser") says
    who or where, not how the reason leads to the conclusion (repair round 4, ADV4-07); "The Treaty of Versailles shaped
    how the Crash and mass unemployment hit Germany" states it ("unemployment")."""
    roots = _roots_of(spans)
    if not (roots & a_roots and roots & b_roots):
        return False
    plain = [t for k, t in enumerate(spans) if not (sentence[t[0]:t[0] + 1].isupper() and (k or lexis.root(t[2]) in names))]
    return bool(_roots_of(plain) & (a_roots | b_roots))


def _connectives(text: str, spans: Sequence[tuple[int, int, str]]) -> list[tuple[str, int, int]]:
    """``(kind, first token, token after)`` of each conclusion ("so", "therefore", ...) or reason ("because", "since", ...)
    connective of one sentence. "so" is one only at a clause start (the sentence's, or after a comma, semicolon, colon or
    "and": "it was so high" is a degree); "because of" is a cause phrase; "since" before a number or a time word is a time."""
    toks = [w for _a, _b, w in spans]
    out: list[tuple[str, int, int]] = []
    for i, cue in lexis.find_cues(toks, CONCLUSION_CONNECTIVES):
        if cue == ("so",):
            before = text[:spans[i][0]].rstrip()
            if not (i == 0 or before.endswith((",", ";", ":", "—", "–")) or (i > 0 and toks[i - 1] == "and")):
                continue
        out.append(("conclusion", i, i + len(cue)))
    for i, cue in lexis.find_cues(toks, REASON_CLAUSE_CONNECTIVES):
        nxt = toks[i + len(cue)] if i + len(cue) < len(toks) else ""
        if cue == ("because",) and nxt == "of":
            continue
        if cue == ("since",) and (not nxt or nxt[0].isdigit() or nxt in _SINCE_TIME_WORDS):
            continue
        out.append(("reason", i, i + len(cue)))
    return sorted(out, key=lambda c: c[1])


#: A ranking of a cause (repair round 5, DA-1): a degree word right before a cause noun ("the main reason", "the chief
#: cause", "the most important factor"), or a degree adverb right before a cause phrase ("mainly because of").
RANKING_DEGREES: frozenset[str] = frozenset({"main", "chief", "principal", "primary", "biggest", "greatest", "key", "leading", "major",
                                             "underlying", "decisive", "dominant", "predominant", "foremost"})
#: Two-word degrees before a cause noun ("the most important reason", "the single biggest cause").
RANKING_DEGREE_PAIRS: frozenset[tuple[str, str]] = frozenset({("most", "important"), ("most", "significant"), ("single", "biggest"),
                                                             ("single", "greatest"), ("single", "main"), ("most", "likely")})
CAUSE_NOUNS: frozenset[str] = frozenset({"reason", "reasons", "cause", "causes", "factor", "factors", "explanation", "driver", "drivers",
                                         "trigger", "source"})
RANKING_ADVERBS: frozenset[str] = frozenset({"mainly", "chiefly", "primarily", "largely", "mostly", "principally", "predominantly"})
#: What follows a degree adverb when it ranks a cause: "mainly because of X", "largely due to X", "chiefly caused by X".
_CAUSE_PHRASES: tuple[tuple[str, ...], ...] = (("because", "of"), ("due", "to"), ("owing", "to"), ("thanks", "to"), ("caused", "by"),
                                               ("as", "a", "result", "of"), ("the", "result", "of"), ("because",))
#: Verbs a ranked cause can be the subject of: "overgrazing mainly causes the soil loss".
_CAUSE_VERBS: frozenset[str] = frozenset({"cause", "causes", "caused", "drive", "drives", "drove", "explain", "explains", "explained"})
_COPULAS: frozenset[str] = frozenset({"is", "was", "are", "were", "remains", "remained", "became", "becomes", "be", "been"})
#: Words of a recommendation (repair round 5, DA-1): the conclusion advises an action.
RECOMMENDATION_WORDS: frozenset[str] = frozenset({"should", "ought", "recommend", "recommends", "recommended", "advise", "advises", "advised"})


def _ranked_item(text: str) -> Optional[frozenset[str]]:
    """The roots of the item a cause-ranking conclusion ranks ("overgrazing" in "overgrazing is the main cause of soil
    loss"; "the Treaty of Versailles" in "the Nazis rose to power mainly because of the Treaty of Versailles"; the
    subject after the copula in "the main reason for the collapse was hyperinflation"), or None when the text ranks no
    cause or denies the ranking ("was not the main reason"). Read on the meaning without its parentheses; linear."""
    toks = list(lexis.tokens(_PAREN_RE.sub(" ", text or "")[:600]))
    if not toks or lexis.negation_markers(toks) > 0:
        return None
    n = len(toks)
    for i, t in enumerate(toks):
        end = None
        if t in RANKING_DEGREES and i + 1 < n and toks[i + 1] in CAUSE_NOUNS:
            end = i + 2
        elif i + 2 < n and (t, toks[i + 1]) in RANKING_DEGREE_PAIRS and toks[i + 2] in CAUSE_NOUNS:
            end = i + 3
        if end is not None:
            before = [k for k in range(i) if toks[k] in _COPULAS]
            if before:  # "X is the main cause (of Y)"
                item = toks[:before[-1]]
            else:       # "the main cause of Y is X"
                after = next((k for k in range(end, n) if toks[k] in _COPULAS), None)
                item = toks[after + 1:] if after is not None else []
            roots = frozenset(_side_roots(" ".join(item)))
            return roots or None
        if t in RANKING_ADVERBS:
            for phrase in _CAUSE_PHRASES:
                if tuple(toks[i + 1:i + 1 + len(phrase)]) == phrase:
                    roots = frozenset(_side_roots(" ".join(toks[i + 1 + len(phrase):])))
                    return roots or None
            if i + 1 < n and toks[i + 1] in _CAUSE_VERBS:
                roots = frozenset(_side_roots(" ".join(toks[:i])))
                return roots or None
    return None


def _recommends(text: str) -> bool:
    """Whether a conclusion advises an action (:data:`RECOMMENDATION_WORDS`: "the firm should open an office in Norway")."""
    return any(t in RECOMMENDATION_WORDS for t in lexis.tokens(_PAREN_RE.sub(" ", text or "")[:600]))


class _LeapShape:
    """How a writer's link may be an unbridged leap (:func:`unbridged_leap_reading`): ``kind`` is ``named`` (two named
    things that share no word), ``ranked`` (a ranking of a cause the reason never mentions) or ``recommended`` (an advised
    action toward a named thing the reason never mentions); ``a`` and ``b`` are the words a joining sentence holds on
    either side of its connective; ``target`` the words of what the conclusion is about that the reason lacks."""
    __slots__ = ("kind", "a", "b", "target")

    def __init__(self, kind: str, a: frozenset[str], b: frozenset[str], target: frozenset[str]) -> None:
        self.kind, self.a, self.b, self.target = kind, a, b, target


def _leap_shape(antecedent: str, consequent: str) -> Optional[_LeapShape]:
    a_roots, b_roots = frozenset(_side_roots(antecedent)), frozenset(_side_roots(consequent))
    if not a_roots or not b_roots:
        return None
    if not a_roots & b_roots and _side_names(antecedent) and _side_names(consequent):
        return _LeapShape("named", a_roots, b_roots, b_roots)
    shared = a_roots & b_roots
    a_rest, b_rest = a_roots - shared, b_roots - shared
    if not a_rest or not b_rest:
        return None
    item = _ranked_item(consequent)
    if item is not None and not item & a_roots:
        # a ranking of a cause, drawn from a reason that never mentions the cause it ranks (repair round 5, DA-1): "the
        # valley has steep slopes, so overgrazing is the main cause of the soil loss"
        return _LeapShape("ranked", a_rest, b_rest, item)
    if _recommends(consequent):
        target = frozenset(_side_names(consequent)) - _side_names(antecedent) - a_roots
        if target:
            # an advised action toward a named thing the reason never mentions (repair round 5, DA-1): "profits rose, so the
            # firm should open an office in Norway"
            return _LeapShape("recommended", a_rest, b_rest, target)
    return None


class _Sentence:
    """One sentence of an answer as the leap reading uses it: its text, tokens, roots, connectives (each with the roots
    on either side of it), whether it holds a control cue, and where it stands in the answer. Built once per answer text
    (:func:`_answer_sentences`)."""
    __slots__ = ("raw", "text", "spans", "roots", "joins", "connective", "control", "start", "end")

    def __init__(self, raw: str, spans, roots: frozenset[str], joins: tuple, connective: bool, control: bool, start: int = 0, end: int = 0) -> None:
        self.raw, self.text, self.spans, self.roots, self.joins = raw, raw.strip(), spans, roots, joins
        self.connective, self.control, self.start, self.end = connective, control, start, end


#: The shortest root a bridge reading compares by its beginning ("occupation" and "occupied", "industry" and
#: "industrial": accuracy round 1, DIFF3-02); a shorter root must be the same root.
_BRIDGE_PREFIX = 5
_MAX_BRIDGE_QUOTES = 64


def _near_root(root: str, roots: frozenset[str]) -> bool:
    """Whether ``root`` is one of ``roots`` or one of them begins the other, both of at least :data:`_BRIDGE_PREFIX`
    letters (a derivation the root reader keeps apart)."""
    if root in roots:
        return True
    return len(root) >= _BRIDGE_PREFIX and any(len(r) >= _BRIDGE_PREFIX and (r.startswith(root) or root.startswith(r)) for r in roots)


def _bridges(text: str, spans: Sequence[tuple[int, int, str]], a_roots: frozenset[str], target: frozenset[str], target_names: frozenset[str],
             names: set[str], offset: int = 0) -> bool:
    """Whether a clause (``spans`` of ``text``) states the connection between a leap's reason and its conclusion (accuracy
    round 1, DIFF3-02): it holds a word of the reason (``a_roots``), a plain word of what the conclusion is about
    (``target``: in lower case, or a first word the answer never writes as a name) and every name of the conclusion's side
    that the reason does not hold (``target_names``), each word read by its root or a derivation of it (:func:`_near_root`).
    "The occupation of the Ruhr crippled German industry" bridges "troops occupied the Ruhr" to "German industrial output
    fell"; "The Wall Street Crash caused mass unemployment in Germany" bridges nothing to "the Treaty of Versailles was the
    main reason ...". Linear in the clause for bounded side tables."""
    roots = [lexis.root(w) for _a, _b, w in spans]
    if not any(_near_root(r, a_roots) for r in roots):
        return False
    if target_names and not target_names <= {r for r in roots}:
        return False
    for k, (a, _b, w) in enumerate(spans):
        name = text[a:a + 1].isupper() and (k + offset or roots[k] in names)  # ``offset``: the clause's first token in its sentence
        if not name and _near_root(roots[k], target):
            return True
    return False


@lru_cache(maxsize=64)
def _quotations(text: str) -> tuple[str, ...]:
    """The quoted spans of ``text`` (the marks :func:`mask_quotations` blanks), read in one pass, at most
    :data:`_MAX_BRIDGE_QUOTES`: the source's words the answer cites, which may state the connection a leap needs."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n and len(out) < _MAX_BRIDGE_QUOTES:
        close = _QUOTES.get(text[i])
        if close is None or (text[i] == "‘" and i > 0 and text[i - 1].isalpha()):
            i += 1
            continue
        j = text.find(close, i + 1, min(n, i + 1 + _MAX_QUOTE))
        if j == -1:
            i += 1
            continue
        out.append(text[i + 1:j])
        i = j + 1
    return tuple(out)


#: Month names: a date the writer adds to the leap's reason ("in January 1923") is no step of the writer's own.
_MONTH_ROOTS = frozenset(lexis.root(m) for m in ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
                                                  "november", "december"))


def _own_step(left: frozenset[str], a_roots: frozenset[str], b_roots: frozenset[str]) -> bool:
    """Whether the reason side of a join (its roots) states something of the writer's own: a content root that neither the
    leap's reason nor its conclusion holds, a number or a month aside (accuracy round 2, V1I-07). "French and Belgian troops
    occupied the Ruhr in 1923, so ..." restates the reason; "The Crash made American banks recall their loans to Germany, so
    ..." states a step between the reason and the conclusion. Not read in a sentence that quotes (its own words attribute the
    quotation: :func:`unbridged_leap_reading`)."""
    return any(r and not r[0].isdigit() and r not in _MONTH_ROOTS for r in left - a_roots - b_roots)


@lru_cache(maxsize=64)
def _answer_sentences(body: str) -> tuple[tuple[_Sentence, ...], frozenset[str]]:
    """The sentences of one masked answer text and the roots of the words it writes as names: read once per text, so the
    reading of every link of a claim costs one pass over the answer (repair round 5, ADV5-01 and ADV5-13). Each join is
    ``(reason roots, conclusion roots)`` read around one connective: the roots before a conclusion connective (or the
    previous sentence's, when it opens the sentence) and after it; for "Since A, B" the clause up to the comma and the rest;
    for "B because A" the words after the connective and before it."""
    out: list[_Sentence] = []
    prev: frozenset[str] = frozenset()
    names: set[str] = set()
    for s, e in _sentence_spans(body):
        sentence = body[s:e]
        spans = lexis.token_spans(sentence)
        for k, (a, _b, w) in enumerate(spans):
            if k and sentence[a:a + 1].isupper():
                names.add(lexis.root(w))
        roots = frozenset(_roots_of(spans))
        joins: list[tuple[frozenset[str], frozenset[str]]] = []
        conns = _connectives(sentence, spans)
        for kind, i, j in conns:
            if kind == "conclusion":
                joins.append((frozenset(_roots_of(spans[:i])) if i else prev, frozenset(_roots_of(spans[j:]))))
            elif i == 0:
                comma = next((k for k in range(j, len(spans)) if "," in sentence[spans[k - 1][1]:spans[k][0]]), None)
                if comma is not None:
                    joins.append((frozenset(_roots_of(spans[j:comma])), frozenset(_roots_of(spans[comma:]))))
            else:
                joins.append((frozenset(_roots_of(spans[j:])), frozenset(_roots_of(spans[:i]))))
        out.append(_Sentence(sentence, spans, roots, tuple(joins), bool(conns), lexis.has_cue(sentence, _CUES.CONTROL) if conns else False, s, e))
        prev = roots
    return tuple(out), frozenset(names)


def unbridged_leap_reading(answer_texts: Sequence[str], antecedent: str, consequent: str) -> Optional[str]:
    """The answer's sentence that joins a writer's link's reason to its conclusion with a bare connective, when the link is
    an unbridged leap, else None (ARG-NS-003). The answer joins the two sides only by a connective ("A, so B", "A.
    Therefore B.", "B because A", "Since A, B"): the reason's words stand on one side of it and the conclusion's on the
    other. The link is a leap of one of three shapes (:func:`_leap_shape`), read on the symbols' meanings with parentheses
    left out:

    * ``named`` (repair round 3): each side names a thing (a capitalised word inside it: "the Wall Street Crash", "the
      Treaty of Versailles") and the two sides share no content word, so the reason is about one named thing and the
      conclusion about another;
    * ``ranked`` (repair round 5, DA-1): the conclusion ranks a cause ("overgrazing is the main cause of the soil loss",
      "... mainly because of X") and the reason shares no word with the cause it ranks, so it says nothing about how that
      cause compares (the sides may share their subject: "the Dunmore valley has steep slopes, so overgrazing is the main
      cause of soil loss in the Dunmore valley");
    * ``recommended`` (repair round 5, DA-1): the conclusion advises an action toward a named thing the reason never
      mentions ("Since Marlpit Ltd's profits rose, Marlpit Ltd should open an office in Norway").

    No sentence of the answer may state the connection itself: a sentence with no connective that holds words of the
    reason and of what the conclusion is about, and not only their names (:func:`_states_connection`: "Doors locked from
    the outside leave the speaker no way out"; "The Treaty of Versailles shaped how the Crash and mass unemployment hit
    Germany"); for the ``recommended`` shape, also any other sentence that says more about the named thing than the
    recommendation does ("Norway has the lowest energy costs in Europe"), since the answer then gives a reason about
    it. A joining sentence with a control cue (random allocation, a control group, a placebo) warrants its causal step and
    is no leap. Quotations are masked: their words are the source's, not the writer's join. A quotation of the answer that
    states the connection bridges the leap (accuracy round 1, DIFF3-02). A join whose reason side states a step of the
    writer's own (:func:`_own_step`) is not read as the leap's join (accuracy round 2, V1I-07). Each answer text is read once
    (:func:`_answer_sentences`, a linear pass), so the reading is linear in the answer for every link."""
    shape = _leap_shape(antecedent, consequent)
    if shape is None:
        return None
    a_roots, b_roots = frozenset(_side_roots(antecedent)), frozenset(_side_roots(consequent))
    originals = [text[:_MAX_LEAP_TEXT] for text in list(dict.fromkeys(t for t in answer_texts if t))[:8]]
    bodies = [mask_quotations(text) for text in originals]
    names = _capitalised_roots(_PAREN_RE.sub(" ", antecedent or "")[:600]) | _capitalised_roots(_PAREN_RE.sub(" ", consequent or "")[:600])
    readings = [_answer_sentences(body) for body in bodies]
    for _sentences, body_names in readings:
        names |= body_names
    bridge_a = shape.a if shape.kind != "named" else a_roots
    # the names of the conclusion's side that the reason lacks: a bridge must speak of each (accuracy round 1, DIFF3-02)
    target_names = frozenset(_side_names(consequent)) - frozenset(_side_names(antecedent)) if shape.kind == "named" else frozenset()
    if shape.kind in ("named", "ranked"):
        # a quotation that states the connection bridges the leap: the answer cites the source for it, and masking hides its
        # words from the connective reading only (accuracy round 1, DIFF3-02: 'Historian K writes that "the occupation of the
        # Ruhr crippled German industry", so German industrial output fell')
        for text in list(dict.fromkeys(t for t in answer_texts if t))[:8]:
            for quoted in _quotations(text[:_MAX_LEAP_TEXT]):
                if _bridges(quoted, lexis.token_spans(quoted), bridge_a, shape.target, target_names, names):
                    return None
    joined: Optional[str] = None
    for original, (sentences, _names) in zip(originals, readings):
        for sent in sentences:
            # a join whose reason side states something of the writer's own beside the leap's reason and its conclusion ("The
            # Crash made American banks recall their loans to Germany, so German unemployment rose") gives a step of its own
            # between them; whether that step bridges the leap is not read, so it is not charged, as on the committed base
            # (accuracy round 2, V1I-07: round 1's reason-clause bridge reading is reverted for its class). In a sentence that
            # quotes, the words around the quotation attribute it ('Historian K writes that "..."'): no step of the writer's own,
            # and the quotation bridge above decides
            quoting = original[sent.start:sent.end] != sent.raw
            joining = [(left, right) for left, right in sent.joins if left & shape.a and right & shape.b
                       and (quoting or not _own_step(left, a_roots, b_roots))]
            if not sent.connective:
                if _states_connection(sent.raw, sent.spans, bridge_a, shape.target, names):
                    return None  # the answer states the connection in a sentence of its own
            if shape.kind == "recommended" and not joining and sent.roots & shape.target and sent.roots - b_roots - a_roots:
                return None  # another sentence says more about the advised target: the answer gives a reason about it
            if not joining or sent.control:
                continue
            if shape.kind == "ranked" and any(left & shape.target for left, _right in joining):
                continue  # the reason names the ranked cause after all
            # the joining sentence as the answer writes it, its quotations shown (masking is the same length as the text)
            joined = joined or (original[sent.start:sent.end].strip() or sent.text)
    return joined


def unbridged_leap(ctx) -> list[NamedDiagnostic]:
    """ARG-NS-003 (module docstring): the point is ENTAILED only through a writer's link (ARG-LINK-001) whose consequent
    is about the point, and the link is an unbridged leap (:func:`unbridged_leap_reading`)."""
    from ..engine.errors import NO_VERDICT_CODES
    from ..engine.statuses import VerificationStatus
    v = ctx.verification
    p = ctx.translation.problem
    if v is None or p is None or p.conclusion is None or v.status is not VerificationStatus.ENTAILED or any(d.code in NO_VERDICT_CODES for d in v.diagnostics):
        return []
    point = set(_expr_atoms(p.conclusion.expr))
    premises = {a.id: a for a in p.premises}
    texts = [ctx.claim.claim_text, *(c.claim_text for c in ctx.supporting)]
    if ctx.report is not None and ctx.report.original_response:
        texts.append(ctx.report.original_response)
    out: list[NamedDiagnostic] = []
    for d in ctx.engine_diagnostics:
        link = d.missing_link
        if d.code != "ARG-LINK-001" or link is None or not link.premise_ids:
            continue
        prem = premises.get(link.premise_ids[0])
        expr = getattr(prem, "expr", None)
        if getattr(expr, "op", None) not in ("implies", "iff") or not (set(_expr_atoms(expr.right)) & point):  # type: ignore[union-attr]
            continue
        sentence = unbridged_leap_reading(texts, link.antecedent, link.consequent)
        if sentence is None:
            continue
        out.append(named_diagnostic(
            "ARG-NS-003", layer="claim", claim_ids=[ctx.claim.claim_id], assertion_ids=list(link.premise_ids), missing_link=link,
            derivation="source_text",
            evidence=[EvidenceSpan(source_kind="claim", source_id=ctx.claim.claim_id[:200], text=sentence[:300])],
            message=(f"leap: the point follows only through the writer's link {', '.join(link.premise_ids[:4])}, from a reason that shares no word with "
                     f"what it concludes; the answer joins them only by a connective ({model_text(sentence, 160)!r}) and states the link nowhere: "
                     f"the missing link is {model_text(link.text, 200)!r}")))
    return out


def _expr_atoms(expr) -> list[str]:
    out: list[str] = []
    stack = [expr]
    steps = 0
    while stack and steps < 4096:
        steps += 1
        node = stack.pop()
        if getattr(node, "op", None) == "var":
            out.append(node.name)
            continue
        for key in ("arg", "left", "right", "cond", "then", "otherwise"):
            child = getattr(node, key, None)
            if child is not None:
                stack.append(child)
        stack.extend(getattr(node, "args", None) or ())
    return out


#: Claim-layer argument rules, run in this order for every outcome (NOT_ELIGIBLE included).
#: Pronouns a reason clause may name its point's subject by ("boring because it is tedious").
_SUBJECT_PRONOUNS = frozenset({"it", "they", "this", "these", "he", "she", "that", "those"})
#: The verbs after which a point's subject ends ("The second chapter is boring": "The second chapter").
_SUBJECT_END_VERBS = frozenset({"is", "are", "was", "were", "has", "have", "had", "seems", "seem", "seemed", "looks", "feels", "becomes", "became"})


def _point_and_reason(text: str) -> Optional[tuple[str, str, bool]]:
    """``(point, reason)`` of a claim that argues in one sentence: "P because R" or "Since R, P"; the reason's pronoun subject
    ("it", "they") read as the point's subject; or, when the claim gives no reason clause, "P <cause phrase> R" with a cause
    phrase of :data:`CAUSE_PHRASES` ("The Berlin Wall fell in 1989 due to the fall of the Berlin Wall in 1989": accuracy
    round 2, V1I-03 and V1-BARE-CIRCULAR, a circular cause the bare-assertion rule no longer names since round 1 reads a
    cause phrase as a reason). The third item is True for a cause phrase. None otherwise."""
    from ..adapters.markdown import leading_reason_clause
    masked = mask_quotations(text or "")[:2000].strip().rstrip(".!?")
    lead = leading_reason_clause(masked)
    cause = False
    if lead is not None:
        comma = masked.find(",", masked.lower().find(lead.lower()) + len(lead))
        point, reason = masked[comma + 1:].strip(), lead
    else:
        m = re.search(r"\s+because\s+(?!of\b)", masked, re.IGNORECASE)
        if m is not None:
            point, reason = masked[:m.start()].strip(" ,"), masked[m.end():].strip()
        else:
            spans = lexis.token_spans(masked)
            found = next(iter(lexis.find_cues([w for _a, _b, w in spans], CAUSE_PHRASES)), None)
            if found is None:
                return None
            i, cue = found
            cause = True
            after = spans[i + len(cue) - 1][1]
            if i == 0:
                # "Due to R, P": the cause runs to the first comma
                comma = masked.find(",", after)
                if comma < 0:
                    return None
                point, reason = masked[comma + 1:].strip(), masked[after:comma].strip()
            else:
                point, reason = masked[:spans[i][0]].strip(" ,"), masked[after:].strip()
    ptoks, rtoks = lexis.tokens(point), lexis.tokens(reason)
    if len(ptoks) < 2 or len(rtoks) < 2:
        return None
    if rtoks[0] in _SUBJECT_PRONOUNS:
        k = next((i for i, t in enumerate(ptoks) if t in _SUBJECT_END_VERBS), None)
        if k is not None and k > 0:
            reason = " ".join(ptoks[:k]) + " " + " ".join(rtoks[1:])
    return point, reason, cause


def own_reason_circle(rctx) -> list[NamedDiagnostic]:
    """ARG-CIRC-003, report layer (repair round 5, ADV5-15 c): a material claim whose own reason clause only restates its
    point ("The second chapter is boring because it is tedious.": the reason is the point in a synonym, read through the
    engine's closed paraphrase tables, :func:`epinoic_logic.engine.argument._restates`), when no engine result decided the
    claim (a claim the translation did not take, as a point with no supporting claims is not): the engine's own reading
    names a circle wherever a result exists. A claim that gives its cause by a cause phrase whose words only restate its point
    ("The Berlin Wall fell in 1989 due to the fall of the Berlin Wall in 1989.") is read too, on every claim the bare-assertion
    rule reads (:func:`_asserts`; accuracy round 2, V1I-03 and V1-BARE-CIRCULAR: since round 1 a cause phrase is a reason to
    that rule, so the circle was no longer named). Read from the claim's characters, nothing executed."""
    from ..engine.argument import _restates
    decided = {o.claim_id for o in rctx.outcomes if getattr(o, "verification", None) is not None}
    pointless = not any(c.materiality == "material" for c in rctx.report.claims)
    out: list[NamedDiagnostic] = []
    for c in rctx.report.claims:
        if c.claim_id in decided or c.claim_role not in ASSERTION_ROLES:
            continue
        pr = _point_and_reason(c.claim_text)
        if pr is None:
            continue
        point, reason, cause = pr
        # a reason clause is read on a material claim; a cause phrase on every claim the bare-assertion rule reads (accuracy
        # round 2: the circle that rule named as a bare assertion before round 1 read a cause phrase as a reason)
        if not (c.materiality == "material" or (cause and _asserts(c, pointless))):
            continue
        if not _restates(reason, False, point, False):
            continue
        out.append(named_diagnostic("ARG-CIRC-003", layer="report", claim_ids=[c.claim_id], derivation="claim_structure",
                                    evidence=[EvidenceSpan(source_kind="claim", source_id=c.claim_id[:200], text=c.claim_text[:300])],
                                    message=(f"circular by paraphrase: claim {c.claim_id} gives as its reason ({model_text(reason, 120)!r}) only its own "
                                             f"point in other words ({model_text(point, 120)!r}): the reason restates the judgement it is meant to support")))
    return out


RULES: tuple[Callable[..., Iterable[NamedDiagnostic]], ...] = (equivocation_flag, circular_refusal, unbridged_leap)
#: Report-layer argument rules, run in this order once per delivered report.
REPORT_RULES: tuple[Callable[..., Iterable[NamedDiagnostic]], ...] = (bare_assertion, own_reason_circle)
