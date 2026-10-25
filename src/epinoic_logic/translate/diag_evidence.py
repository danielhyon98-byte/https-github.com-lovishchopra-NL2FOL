"""Claim and report rules of the evidence family (rules ``argdiag-2``), and the source-bound reading of a request.

``RULES`` are claim-layer rules, ``rule(ctx: diag_core.DiagContext) -> Iterable[NamedDiagnostic]``; ``REPORT_RULES`` are
report-layer rules, ``rule(rctx: diag_core.ReportContext) -> Iterable[NamedDiagnostic]``. :mod:`.diag_core` runs them after
the argument rules, guards each one, and applies the caps: a code whose ``warning_scope`` is ``source_bound`` is shown at
warning only when :func:`source_bound` holds for the request (``source_bound_or_data``: also when
:func:`supplies_data_texts` holds for the report), and is capped at info, with ``capped_from`` recorded, otherwise. A capped
warning still blocks release.

The claim rules grade the premises the point NEEDS: the premises R0 names (``ctx.needed_premises``: the assertion ids of
ARG-LINK-001 and ARG-FACT-001), or, when R0 named none, the premises the trusted engine result relied on (its core). A
premise's authority is read from the grounding records of this process only (``engine.authority.has_authority`` through
the premise roles), never from its label:

* ``EVD-SRC-001`` (unchecked_source): a needed fact premise whose kind claims a text or task authority (quotation,
  supplied_text, knowledge_document, library_source, task_setting, rubric_rule, arithmetic_fact) that no check verified,
  or a needed link that claims one and cites no reference at all; a task-authority premise that restates a supposition
  the task sets for the answer ("Assume that ...", "Suppose ...") is not named (close round 3, DV2-04);
* ``EVD-SRC-005`` (unchecked_source, warning in every task): a needed premise, fact or link, whose kind claims the
  task's authority (task_setting, rubric_rule, arithmetic_fact), that cites no excerpt, and that the task material does
  not hold (its grounding check refuted it);
* ``EVD-SRC-003`` (source_mismatch): a needed premise whose grounding check failed;
* ``EVD-SRC-004`` (unchecked_source, info): the provider wrote its own ``verified: true`` on a grounding, which was
  discarded (every translation, whatever its status);
* ``EVD-LACK-001`` (lack_of_evidence): a needed fact premise that claims no source (general knowledge, the specialist's
  inference, an assumption, no grounding) and that no check verified;
* ``EVD-FIG-001`` (invented_figure): a needed assignment whose figure occurs in no supplied text and not in the task
  record, is no result of a written calculation, and carries no from-memory label;
* ``EVD-AUTH-001`` (uncheckable_authority): a needed premise that no check verified and that leans on an unattributed
  authority or data cue ("leading economists agree", "survey data show", "it is widely accepted"), or on one person's
  authority with no year and no supplied text of theirs ("the historian Margaret Hale has shown");
* ``EVD-CHERRY-001`` (cherry_picked_data): the point names a period ("from 2010 to 2020", "2010 to 2020", "2010-2020",
  "since 2010"; or months of a year, "between January and June", "January-June", "the first half of the year", "the first
  six months"), a supplied text gives values for both of its end years (or months), the encoding or the evidence claim
  uses only time points of the period and leaves at least one of its ends out, and with the period's own end values the
  point's direction ("rose", "recovered", "rebounded"; "fell", "declined", "slumped") fails.

The first five apply to an ENTAILED result that is a verdict (no E108, E110, E111 or E112); EVD-CHERRY-001 to any decided
result; EVD-SRC-004 to every translation. The report rules:

* ``EVD-SRC-006`` (source_mismatch, warning; repair round 2): a claim attributes content to a named supplied document,
  the attributed content states one stance only (approving or disapproving: a closed table, negation read), the document
  states only the opposite stance, and the two share a content word beyond the stance words: the source is cited for the
  opposite of what it says;

and, info only (a paraphrase cannot be checked deterministically, so they say "not checked", never "false"):

* ``EVD-SRC-002`` (unchecked_source): a claim attributes content to a named supplied document ("Source A shows that
  ..."), no quotation of its answer section is located in a supplied text, and most of the attributed content's words do
  not occur in that document;
* ``EVD-LACK-002`` (lack_of_evidence): in a task with supplied texts, a claim states a change in a quantity with no
  figure, and no content word of what changed occurs in a supplied text or in the request.

:func:`source_bound` says whether a request names supplied material as the basis of the answer ("using the extract",
"according to the text", "with reference to Source A", ...): a closed cue list read with :mod:`epinoic_logic.lexis`.
Without a task record a request is never source-bound, so its evidence diagnostics are info: the conservative reading.

Every rule reads validated IR, the grounding records, the claims and the request as data, through the shared tokenizer and
bounded linear scans; nothing is evaluated or executed. A diagnostic only adds: it never changes a status, a dependency
list, a grounding check or a finding, and can only make a result less releasable.
"""
from __future__ import annotations

from functools import lru_cache

import re
from fractions import Fraction
from typing import Any, Callable, Iterable, Optional, Sequence

from ..engine.errors import NO_VERDICT_CODES
from ..engine.statuses import DEFINITIVE, VerificationStatus
from ..lexis import content_stems, cue_table, find_cues, has_cue, token_spans
from ..named import EvidenceSpan, NamedDiagnostic, cap, model_text, named_diagnostic
from ..lexis import root as lexis_root
from ..lexis import negated as lexis_negated
from ..lexis import tokens as lexis_tokens
from .assertion import sentence_cue_at
from .grounding import AUTHORITY_LABEL_WORDS, FORM_DIFFERS, NOTATION_WORDS, spells_notation
from .quantities import _sentences  # the cached sentence spans of a record (shared with the grounding readers)
from .stated_rules import meaning_roots

__all__ = [
    "RULES", "REPORT_RULES", "source_bound", "supplies_data_texts",
    "SOURCE_BOUND_CUES", "AUTHORITY_NOUNS", "AUTHORITY_VERBS", "AUTHORITY_PHRASES", "AUTHORITY_PERSONS", "AUTHORITY_PERSON_VERBS", "TREND_VERBS",
    "ATTRIBUTION_VERBS",
    "ATTRIBUTION_KINDS", "TEXT_AUTHORITY_KINDS", "TASK_AUTHORITY_KINDS", "WRITER_KINDS", "FALLING_WORDS", "RISING_WORDS", "DATA_TITLE_WORDS",
    "evd_src_001", "evd_src_003", "evd_src_004", "evd_src_005", "evd_lack_001", "evd_fig_001", "evd_auth_001", "evd_cherry_001",
    "evd_src_002", "evd_lack_002", "evd_src_006", "APPROVING_WORDS", "DISAPPROVING_WORDS", "NOTATION_WORDS",
]

# ----------------------------------------------------------------------------------------------- the closed tables

#: A request is source-bound when it names supplied material as the basis of the answer (one of these token sequences, on
#: word boundaries; ``*`` is any one token, as in "what does Source A suggest").
SOURCE_BOUND_CUES: tuple[str, ...] = (
    "using the extract", "using the extracts", "using extract", "using the source", "using the sources", "using source", "using sources",
    "using the text", "using the texts", "using the passage", "using the table", "using table", "using the data", "using data",
    "using the figure", "using figure", "using the study summary", "using the study", "using the graph", "using graph", "using the article",
    "with reference to source", "with reference to sources", "with reference to the source", "with reference to the sources",
    "with reference to the extract", "with reference to the text", "with reference to the passage", "with reference to the table",
    "with reference to table", "with reference to the data", "with reference to the figure", "with reference to figure",
    "with reference to the article", "with reference to the study",
    "according to the text", "according to the extract", "according to the source",
    "what does source * suggest", "what does source * show", "what does source * reveal", "what does source * tell us",
    "what does the extract suggest", "what does the extract show", "what does the extract reveal", "what does the extract tell us",
    "in this extract", "in the extract", "in this passage", "in the passage", "in this poem", "in the poem",
    "from the table", "from the data", "from the extract",
    "refer to the", "refer to source", "refer to sources", "refer to table", "refer to figure", "refer to extract",
    # repair round 1 (re-run review ADV-12): the common phrasings that name a supplied text or document as the basis
    "using text", "using texts", "using document", "using documents", "using the document", "using the documents", "using the sources provided",
    "compare source", "compare sources", "compare the source", "compare the sources", "compare text", "compare texts", "compare the texts",
    "compare document", "compare documents", "compare the documents",
    "based on the extract", "based on the extracts", "based on extract", "based on the text", "based on the texts", "based on text",
    "based on the source", "based on the sources", "based on source", "based on sources", "based on the passage", "based on the data",
    "based on data", "based on the table", "based on table", "based on the figure", "based on figure", "based on the article",
    "based on the study", "based on the document", "based on document", "based on the documents",
    "with reference to text", "with reference to texts", "with reference to document", "with reference to documents",
    "with reference to the document", "with reference to the documents",
    "according to text", "according to source", "according to the article", "according to the passage", "according to the data",
    "according to the table", "according to the figure", "according to document", "according to the document",
    "use the extract", "use the text", "use the source", "use the sources", "use source", "use sources", "use the data", "use the table",
    "use the document", "use document", "use the passage", "use the article",
    "what does text * suggest", "what does text * show", "what does document * suggest", "what does document * show",
    "how useful is source", "how reliable is source", "how far does source", "how useful are sources",
)
_SOURCE_BOUND = cue_table(SOURCE_BOUND_CUES)

#: The authorities and data an unattributed appeal names ("economists", "studies", "survey data"), the verbs that make the
#: appeal ("agree", "show", "suggest", "prove", "confirm", "indicate", "have shown") and the fixed phrases of the same kind.
AUTHORITY_NOUNS: tuple[str, ...] = ("experts", "economists", "scientists", "historians", "researchers", "psychologists", "studies", "research",
                                    "surveys", "statistics", "data")
AUTHORITY_VERBS: tuple[str, ...] = ("agree", "show", "shows", "suggest", "suggests", "prove", "proves", "confirm", "confirms", "indicate", "indicates")
AUTHORITY_PHRASES: tuple[str, ...] = tuple(
    [f"it is {a} {p}" for a in ("widely", "generally", "commonly") for p in ("accepted", "agreed", "known", "believed")]
    + ["it is well known"]
    + [f"according to {n}" for n in AUTHORITY_NOUNS if n != "data"] + ["according to the data"])
_AUTHORITY_CUES = cue_table([f"{n} {v}" for n in AUTHORITY_NOUNS for v in AUTHORITY_VERBS]
                            + [f"{n} {h} shown" for n in AUTHORITY_NOUNS for h in ("have", "has")])
#: One authority, named or not, and the verbs of its finding ("the historian Margaret Hale has shown", "one expert argues"):
#: a named person with no year and no supplied text of theirs is no checkable source (repair round 1, re-run review
#: A-EVD-AUTH). Up to three name tokens may stand between the noun and the verb.
AUTHORITY_PERSONS: tuple[str, ...] = ("historian", "economist", "scientist", "expert", "researcher", "psychologist", "professor", "analyst",
                                      "sociologist", "biologist", "physicist", "geographer", "commentator", "scholar", "academic")
AUTHORITY_PERSON_VERBS: tuple[str, ...] = (
    "has shown", "has argued", "has proved", "has proven", "has demonstrated", "has established", "has found", "has concluded", "showed",
    "shows", "argues", "argued", "proves", "proved", "demonstrated", "demonstrates", "established", "found", "concluded", "concludes",
    "claims", "claimed", "suggests", "suggested", "contends", "maintains")
_AUTHORITY_PERSON_CUES = cue_table([f"{n}{' *' * k} {v}" for n in AUTHORITY_PERSONS for k in range(4) for v in AUTHORITY_PERSON_VERBS])
_AUTHORITY_FIXED = cue_table(AUTHORITY_PHRASES)
#: Words that, right before an authority cue, point to a specific source ("the data show" in a task that supplies data).
_DEFINITE = frozenset({"the", "this", "these", "that", "those", "our", "my", "its", "their"})
#: A named author with a year ("Loftus and Palmer (1974)", "Smith et al. (2019)"): an attributed source, not an anonymous one.
_NAMED_AUTHOR_YEAR_RE = re.compile(r"\b[A-Z][a-z]{1,40}(?:\s+(?:and|&)\s+[A-Z][a-z]{1,40})?(?:\s+et\s+al\.?)?,?\s+\(?(?:1[0-9]{3}|20[0-9]{2})\)?")

#: Verbs that state a change in a quantity (EVD-LACK-002).
TREND_VERBS: frozenset[str] = frozenset({
    "rose", "risen", "rises", "fell", "fallen", "falls", "increased", "increases", "decreased", "decreases", "grew", "grown", "grows",
    "declined", "declines", "dropped", "drops", "climbed", "doubled", "halved", "slowed", "accelerated"})
#: Verbs of an attribution to a document (EVD-SRC-002), and the kinds a document may be named by.
ATTRIBUTION_VERBS: frozenset[str] = frozenset({"shows", "show", "suggests", "states", "says", "reveals", "indicates", "proves"})
ATTRIBUTION_KINDS: frozenset[str] = frozenset({"extract", "table", "text", "passage", "study", "source"})
#: The direction words of a point about a period (EVD-CHERRY-001).
FALLING_WORDS: frozenset[str] = frozenset({"fell", "fall", "falls", "fallen", "falling", "declined", "decline", "declines", "declining", "decreased",
                                           "decrease", "decreases", "decreasing", "dropped", "drop", "drops", "dropping", "downward", "shrank",
                                           "contracted", "slumped", "plummeted", "plunged", "dipped", "sank", "halved"})
RISING_WORDS: frozenset[str] = frozenset({"rose", "rise", "rises", "risen", "rising", "increased", "increase", "increases", "increasing", "grew", "grow",
                                          "grows", "growing", "climbed", "climbing", "upward", "recovered", "recover", "recovers", "recovering",
                                          "rebounded", "rebound", "rebounds", "rebounding", "soared", "surged", "jumped", "expanded",
                                          # repair round 2: a fold of growth is a rise ("more than quadrupled over the decade")
                                          "doubled", "tripled", "trebled", "quadrupled", "quintupled"})
#: Words of a supplied text's title or id that name it as data (EVD-FIG-001's second warning condition).
DATA_TITLE_WORDS: frozenset[str] = frozenset({"table", "data", "dataset", "figure", "chart", "graph", "statistics", "survey", "results"})

#: Grounding kinds that claim a text's or the task's authority, the kinds that claim the task's, and the kinds that claim
#: no source.
TEXT_AUTHORITY_KINDS: frozenset[str] = frozenset({"quotation", "supplied_text", "knowledge_document", "library_source", "task_setting", "rubric_rule",
                                                  "arithmetic_fact"})
TASK_AUTHORITY_KINDS: frozenset[str] = frozenset({"task_setting", "rubric_rule", "arithmetic_fact"})
WRITER_KINDS: frozenset[str] = frozenset({"general_knowledge", "specialist_inference", "assumption"})

_MONTHS = frozenset("january february march april may june july august september october november december".split())
#: How many attributed-content stems of a claim must occur in the named document (EVD-SRC-002), and the least it must have.
_ATTRIBUTION_SHARE = Fraction(3, 5)
_ATTRIBUTION_MIN_STEMS = 3
#: Bounds of the scans (inputs are already bounded by their schemas; these keep every rule linear and small).
_MAX_TEXT = 400_000
_MAX_CLAIMS = 512
_MAX_EVIDENCE_CHARS = 300
_MAX_NAMED = 8


# ----------------------------------------------------------------------------------------------- shared readers

def _tokens(text: str) -> list[tuple[int, int, str]]:
    return list(token_spans((text or "")[:_MAX_TEXT]))


def _is_year(tok: str) -> bool:
    return len(tok) == 4 and tok.isdecimal() and 1000 <= int(tok) <= 2199


def _is_number(tok: str) -> bool:
    return tok[:1].isdecimal()


def _number_value(tok: str) -> Optional[Fraction]:
    body = tok.replace(",", "")
    if not body or len(body) > 40 or body.count(".") > 1:
        return None
    try:
        return Fraction(body)
    except (ValueError, ZeroDivisionError):
        return None


def _masked(text: str) -> str:
    """``text`` with every quoted span masked (its words are another text's, never the writer's own statement)."""
    from ..adapters.markdown import mask_quotations
    return mask_quotations((text or "")[:_MAX_TEXT])


def _stems(text: str) -> set[str]:
    return set(content_stems(text or ""))


@lru_cache(maxsize=32)
def _text_stems(text: str) -> frozenset[str]:
    """The content stems of a supplied text, computed once per text (repair round 2, ADV2-01: every attribution of every claim
    read the whole document again, so a long source and many attributions cost their product)."""
    return frozenset(content_stems(text or ""))


def _cut(text: str, limit: int = _MAX_EVIDENCE_CHARS) -> str:
    """Model or record text as a message shows it: one line, the forgery words masked (``named.model_text``)."""
    return model_text(text or "", limit)


def _raw(text: str, limit: int = _MAX_EVIDENCE_CHARS) -> str:
    s = " ".join((text or "").split())
    return s if len(s) <= limit else s[: limit - 3].rstrip() + "..."


def _span(kind: str, source_id: str, text: str, start: Optional[int] = None, end: Optional[int] = None) -> EvidenceSpan:
    return EvidenceSpan(source_kind=kind, source_id=(source_id or "unknown")[:200], start=start, end=end, text=_raw(text))  # type: ignore[arg-type]


def source_bound(task_text: Optional[str]) -> bool:
    """Whether the request names supplied material as the basis of the answer (:data:`SOURCE_BOUND_CUES`, on word
    boundaries; module docstring). No task record: never source-bound."""
    if not task_text or not task_text.strip():
        return False
    return has_cue(task_text[:_MAX_TEXT], _SOURCE_BOUND)


def _is_data_text(doc: Any) -> bool:
    """A supplied text that is data: its title or id names a table, data, a figure, a chart or statistics, or it states two
    or more figures other than years."""
    name = " ".join(x for x in (getattr(doc, "title", None) or "", getattr(doc, "document_id", "") or "") if x)
    if {t for _s, _e, t in token_spans(name)} & DATA_TITLE_WORDS:
        return True
    figures = 0
    for _s, _e, tok in token_spans((getattr(doc, "text", "") or "")[:_MAX_TEXT]):
        if _is_number(tok) and not _is_year(tok):
            figures += 1
            if figures >= 2:
                return True
    return False


def supplies_data_texts(report: Any) -> bool:
    """Whether the report's supplied texts include a data text (:func:`_is_data_text`): the second condition under which
    ``EVD-FIG-001`` is shown at warning."""
    return any(_is_data_text(t) for t in (getattr(report, "supplied_texts", None) or ()))


# ----------------------------------------------------------------------------------------------- claim context readers

def _is_verdict(ctx: Any, statuses: frozenset) -> bool:
    v = ctx.verification
    return v is not None and v.status in statuses and not any(d.code in NO_VERDICT_CODES for d in v.diagnostics)


def _entailed(ctx: Any) -> bool:
    return _is_verdict(ctx, frozenset({VerificationStatus.ENTAILED}))


def _decided(ctx: Any) -> bool:
    return _is_verdict(ctx, DEFINITIVE)


def _needed(ctx: Any) -> list[str]:
    """The premises the point needs: R0's (links and facts), else the trusted result's core."""
    ids = ctx.needed_premises if ctx.needed_premises is not None else ctx.core
    return list(dict.fromkeys(ids))


def _premise_map(ctx: Any) -> dict[str, Any]:
    p = ctx.translation.problem
    return {a.id: a for a in p.premises} if p is not None else {}


def _symbols(ctx: Any) -> dict[str, Any]:
    p = ctx.translation.problem
    return {s.name: s for s in p.symbols} if p is not None else {}


def _roles(ctx: Any) -> dict[str, Any]:
    return {r.assertion_id: r for r in ctx.premise_roles}


def _atoms(expr: Any) -> list[str]:
    """The symbol names of an IR expression (a bounded walk over the validated model; nothing is evaluated)."""
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
    return list(dict.fromkeys(out))


def _gloss(premise: Any, symbols: dict[str, Any]) -> str:
    """A premise's label and its symbols' meanings: what its words are read on."""
    parts = [premise.label or ""]
    for name in _atoms(premise.expr):
        sym = symbols.get(name)
        if sym is not None and sym.meaning:
            parts.append(sym.meaning)
    return " ".join(p for p in parts if p)


def _needed_with_role(ctx: Any, role: Optional[str] = None) -> list[tuple[Any, Any]]:
    """``(premise, its PremiseRole)`` for each needed premise (of role ``role`` when given)."""
    premises, roles = _premise_map(ctx), _roles(ctx)
    out = []
    for pid in _needed(ctx):
        p, r = premises.get(pid), roles.get(pid)
        if p is None or r is None or (role is not None and r.role != role):
            continue
        out.append((p, r))
    return out


def _claim_spans(ctx: Any) -> list[EvidenceSpan]:
    return [_span("claim", ctx.claim.claim_id, ctx.claim.claim_text)]


def _premise_span(p: Any, symbols: dict[str, Any]) -> EvidenceSpan:
    return _span("premise_label", p.id, p.label or _gloss(p, symbols) or p.id)


def _names(items: Sequence[str]) -> str:
    shown = ", ".join(items[:_MAX_NAMED])
    return shown + (f" and {len(items) - _MAX_NAMED} more" if len(items) > _MAX_NAMED else "")


# ----------------------------------------------------------------------------------------------- claim rules

def _refuted_task_label(p: Any, r: Any) -> bool:
    """A premise of a task-authority kind that cites no excerpt and that the task material refuted (EVD-SRC-005)."""
    return r.kind in TASK_AUTHORITY_KINDS and r.authority == "refuted" and _label_only(p)


#: At most this many sentences of the task record are read for a supposition the task sets, each cut at this many characters.
_MAX_SUPPOSITION_SENTENCES = 400
_MAX_SUPPOSITION_CHARS = 2000
_AUTHORITY_ROOTS = frozenset(lexis_root(w) for w in AUTHORITY_LABEL_WORDS)


@lru_cache(maxsize=64)
def _task_suppositions(task_text: str) -> tuple[tuple[frozenset[str], bool], ...]:
    """``(roots, negated)`` of every sentence of the task record whose opening construction is a supposition the task sets
    for the answer ("Assume that ...", "Suppose ...", "Imagine ...", "Assuming ...": the supposition mood of
    ``assertion.sentence_cue_at``). Bounded: the first :data:`_MAX_SUPPOSITION_SENTENCES` sentences, each cut at
    :data:`_MAX_SUPPOSITION_CHARS`; one linear pass, cached per task text."""
    text = task_text[:_MAX_TEXT]
    out: list[tuple[frozenset[str], bool]] = []
    for a, b in _sentences(text)[:_MAX_SUPPOSITION_SENTENCES]:
        sentence = text[a:min(b, a + _MAX_SUPPOSITION_CHARS)]
        lead = a + (len(sentence) - len(sentence.lstrip()))
        cue = sentence_cue_at(text, lead) if sentence.strip() else None
        if cue is None or cue[0] != "supposition":
            continue
        out.append((frozenset(lexis_root(t) for t in lexis_tokens(sentence)), lexis_negated(sentence)))
    return tuple(out)


def _supposed_by_task(p: Any, symbols: dict[str, Any], task_text: Optional[str]) -> bool:
    """Whether a premise restates a supposition the task sets for the answer (close round 3, DV2-04): one sentence of the
    task record that opens with a supposition (:func:`_task_suppositions`) holds every content root of the premise's words
    (its symbols' meanings, else its label, without the words that name an authority) with the premise's polarity. The
    task then gives the premise as the scenario the answer is to reason in, so the premise does not rest on a label alone,
    and EVD-SRC-001 does not name it; its grounding record is unchanged (the authority stays unvalidated, so the result is
    still not releasable on it). A plain restriction of EVD-SRC-001's trigger set: it never adds a diagnostic."""
    if not task_text:
        return False
    suppositions = _task_suppositions(task_text)
    if not suppositions:
        return False
    meanings = " ".join((symbols[n].meaning or "") for n in _atoms(p.expr) if n in symbols and symbols[n].meaning)
    words = meanings if meanings.strip() else (p.label or "")
    wanted = meaning_roots(words) - _AUTHORITY_ROOTS
    if not wanted:
        return False
    negative = (getattr(p.expr, "op", None) == "not") != lexis_negated(words)
    return any(wanted <= roots and negated == negative for roots, negated in suppositions)


#: Words by which a task sentence says that something was only expected, predicted, hoped for or intended, not done
#: ("although commentators had expected it to raise interest rates"): a clause that holds one states no given (accuracy round 2,
#: V1-RESTATE-SUSPENDED). After "than" or "as" the word states what happened ("Sales rose faster than expected."), and after a
#: determiner it names a thing ("the expected rise", "the forecast"), not an expectation of the clause.
_UNREALISED_WORDS = frozenset("""
expect expects expected expecting anticipate anticipates anticipated anticipating predict predicts predicted predicting forecast forecasts
forecasting hope hopes hoped hoping intend intends intended intending
""".split())
_UNREALISED_EXEMPT_BEFORE = frozenset({"than", "as", "the", "a", "an", "its", "their", "his", "her", "this", "that", "these", "those", "our"})
#: Pronouns by which a clause speaks of what a clause before it named ("as a result, its sales dropped").
_CONTINUING_PRONOUNS = frozenset({"it", "its", "they", "their", "them"})
#: Words that open a relative clause: a relative clause that suspends ("The bridge, which was expected in 2010, opened in
#: 2015.") suspends only itself, not the clauses after it.
_RELATIVE_OPENERS = frozenset({"which", "who", "whom", "whose"})


#: One sentence of the task record as :func:`_asserted_by_task` reads it: its statements ``(roots, negated, suspended)`` (the
#: sentence, and for a suspended one the clauses that state the task's own given) and its asserted clauses, each as the change
#: readings use it (``grounding.change_clause``).
_TaskSentence = tuple[tuple[tuple[frozenset[str], bool, bool], ...], tuple[Any, ...]]


@lru_cache(maxsize=64)
def _task_statements(task_text: str) -> tuple[_TaskSentence, ...]:
    """Every sentence of the task record as :func:`_asserted_by_task` reads it (accuracy round 2, V1I-02): its statements
    ``(roots, negated, suspended)``, ``suspended`` when a question, an instruction or a supposition opens the sentence
    (``assertion.sentence_cue_at``), it ends with "?", or it holds a word by which the grounding reader suspends a statement,
    reports a view or attributes a judgement (``grounding.SUSPENDING_TASK_WORDS``, ``REPORTED_VIEW_WORDS``,
    ``ATTRIBUTING_TASK_WORDS``: the closed lists) or a word of :data:`_UNREALISED_WORDS` (V1-RESTATE-SUSPENDED); a suspended
    sentence that no question or instruction opens also gives the clauses that state the task's own given, those before the
    first clause that suspends (a suspending relative clause suspends only itself), as one statement. And its asserted clauses
    (every clause of an unsuspended sentence; those kept clauses of a suspended one), each with the words of a change it holds
    (``grounding.change_clause``). Bounded as :func:`_task_suppositions`; one linear pass, cached per task text."""
    from .grounding import (ATTRIBUTING_TASK_WORDS, REPORTED_VIEW_WORDS, SUSPENDING_TASK_WORDS, _MAX_CHANGE_CLAUSES, _TASK_CLAUSE_RE,
                            _suspending_tokens, change_clause)
    text = task_text[:_MAX_TEXT]
    out: list[_TaskSentence] = []

    def suspends(part: str) -> bool:
        toks = _suspending_tokens(part)
        return any(t in SUSPENDING_TASK_WORDS or t in REPORTED_VIEW_WORDS or t in ATTRIBUTING_TASK_WORDS
                   or (t in _UNREALISED_WORDS and not (i and toks[i - 1] in _UNREALISED_EXEMPT_BEFORE)) for i, t in enumerate(toks))

    def statement(part: str, suspended: bool) -> tuple[frozenset[str], bool, bool]:
        return frozenset(meaning_roots(part)), lexis_negated(part), suspended

    for a, b in _sentences(text)[:_MAX_SUPPOSITION_SENTENCES]:
        sentence = text[a:min(b, a + _MAX_SUPPOSITION_CHARS)]
        if not sentence.strip():
            continue
        lead = a + (len(sentence) - len(sentence.lstrip()))
        opened = sentence.rstrip().endswith("?") or sentence_cue_at(text, lead) is not None
        suspended = opened or suspends(sentence)
        statements = [statement(sentence, suspended)]
        parts = [part for part in _TASK_CLAUSE_RE.split(sentence)[:_MAX_CHANGE_CLAUSES] if part.strip()]
        kept: list[str] = []
        if not suspended:
            kept = parts
        elif not opened:
            # the clauses before the first one that suspends are the task's own statement ("The government raised the minimum
            # wage, and economists say this will reduce hiring." asserts its first clause)
            for part in parts:
                if suspends(part):
                    if next(iter(lexis_tokens(part)), "") in _RELATIVE_OPENERS:
                        continue  # a relative clause suspends only itself
                    break
                kept.append(part)
            if kept:
                statements.append(statement(" ".join(kept), False))
        out.append((tuple(statements), tuple(change_clause(part) for part in kept)))
    return tuple(out)


def _asserted_by_task(p: Any, symbols: dict[str, Any], task_text: Optional[str]) -> bool:
    """Whether a sentence of the task record that holds a task-authority premise's words states them as the task's own
    (accuracy round 2, V1I-02 and V1-RESTATE-SUSPENDED): one statement of a sentence (:func:`_task_statements`) holds all of the
    premise's content roots but one (and at least two), with the premise's polarity, and no word of the closed lists, nor one
    of :data:`_UNREALISED_WORDS`, suspends it; and the premise's own verb of a change, which is never the one left out, is the
    change an asserted clause of that sentence states of the premise's own subject: the clause holds another of the
    premise's words and the verb itself, or, in other words, a change of its direction nearest to them
    (``grounding._held_change_roots``: "the firm lowered its costs" for "the firm drove its costs down"; not "the central bank
    lowered interest rates" for "After inflation fell, the central bank raised interest rates", nor "increased interest
    rates" for "kept interest rates unchanged"). A change held only in other words leaves no word of the premise out but one a
    pronoun of the sentence stands for ("unemployment in Country Y declined" is no restatement of "Unemployment in Country Z
    fell"; "the firm's sales fell" restates "as a result, its sales dropped"). The premise then restates, perhaps in other words, what the task asserts, which this layer cannot tell from a
    misreading of it: EVD-SRC-001 records it at info instead of charging it (the committed base names nothing), and its
    grounding record is unchanged, so the result is still not releasable on it. A premise the task holds only in a hedge, a
    condition, a report, a supposition, an expectation, of another subject or with the other polarity is still named at
    warning."""
    if not task_text:
        return False
    sentences = _task_statements(task_text)
    if not sentences:
        return False
    from .grounding import _held_change_roots, direction_verbs
    meanings = " ".join((symbols[n].meaning or "") for n in _atoms(p.expr) if n in symbols and symbols[n].meaning)
    words = meanings if meanings.strip() else (p.label or "")
    wanted = meaning_roots(words) - _AUTHORITY_ROOTS
    if len(wanted) < 2:
        return False
    negative = (getattr(p.expr, "op", None) == "not") != lexis_negated(words)
    p_rise, p_fall = direction_verbs(lexis_tokens(words))
    change = {lexis_root(w) for t in p_rise | p_fall for w in t.split()} & wanted
    others = wanted - change
    for statements, clauses in sentences:
        held_change: set[str] = set()
        if change:
            held_change = _held_change_roots(words, clauses, wanted) & change
            held_change |= {r for r in change if any(r in c_roots and c_roots & others for c_roots, _toks, _marks in clauses)}
            if not change <= held_change:
                continue  # the premise's own change is not one an asserted clause of this sentence states of its subject
        # a pronoun of the sentence may stand for one word of the premise ("The firm increased its prices; as a result, its
        # sales dropped." for "the firm's sales fell")
        pronoun = any(c_roots & _CONTINUING_PRONOUNS for c_roots, _toks, _marks in clauses)
        for roots, negated, suspended in statements:
            held = (wanted & roots) | held_change
            # a change held only in other words stands for no other word but one a pronoun stands for: the rest of the premise is
            # then held in full ("Country Y declined" for "Country Z fell" is no restatement)
            if held_change - roots:
                enough = held == wanted or (pronoun and len(wanted - held) == 1)
            else:
                enough = len(held) >= max(2, len(wanted) - 1)
            if enough and not suspended and negated == negative:
                return True
    return False


def evd_src_001(ctx: Any) -> Iterable[NamedDiagnostic]:
    """EVD-SRC-001: a needed fact premise claims a text or task authority that no check verified (a label with no excerpt,
    an empty excerpt, or an excerpt no check located), or a needed link claims one with no reference at all (repair
    round 1, re-run review ADV-11 f: a link labelled with a source it never cites) or only with excerpts that are located
    but state none of its connective (repair round 3, ADV3-13: "Britain" or "Explain your answer." cited for the writer's
    'if the navy was largest, Britain was certain to win'): the point rests on a source label alone. A task-authority
    label the task material refuted is EVD-SRC-005's. A task-authority premise that restates a supposition the task sets
    ("Assume that interest rates will rise next year.", :func:`_supposed_by_task`) is not named: the task gives it as the
    answer's scenario (close round 3, DV2-04: correct work that takes the supposition as given was named unchecked_source
    at warning, where the committed base names nothing). A label-only task-authority premise whose words a sentence the task
    asserts holds (:func:`_asserted_by_task`) is recorded at info, not charged: it may restate the task's fact in other words,
    which no check here reads (accuracy round 2, V1I-02 and V1-RESTATE-SUSPENDED: round 1 dropped such premises through a
    restatement reader of synonym tables, which still charged some true restatements and dropped a premise that adopts what
    the task says was only expected; the reader is removed, and the record keeps the premise named and blocked)."""
    if not _entailed(ctx):
        return ()
    symbols = _symbols(ctx)
    hit = [(p, r) for p, r in _needed_with_role(ctx)
           if r.kind in TEXT_AUTHORITY_KINDS and not _refuted_task_label(p, r)
           and ((r.role == "fact" and (r.authority == "unverified" or (r.authority == "refuted" and _label_only(p))))
                or (r.role != "fact" and r.authority in ("unverified", "refuted") and _label_only(p))
                or (r.role != "fact" and r.authority == "unverified" and _cites_words_not_the_link(p, ctx)))
           and not (r.kind in TASK_AUTHORITY_KINDS and r.authority == "unverified" and _supposed_by_task(p, symbols, ctx.task_text))]
    if not hit:
        return ()
    # a label-only task premise whose words a sentence the task asserts holds is recorded, not charged (accuracy round 2, V1I-02:
    # round 1's restatement reading, which dropped such a premise, is reverted to this record)
    restated = [(p, r) for p, r in hit if r.kind in TASK_AUTHORITY_KINDS and r.authority == "unverified" and _label_only(p)
                and _asserted_by_task(p, symbols, ctx.task_text)]
    charged = [(p, r) for p, r in hit if (p, r) not in restated]
    out: list[NamedDiagnostic] = []
    if charged:
        ids = [p.id for p, _r in charged]
        kinds = sorted({r.kind for _p, r in charged if r.kind})
        out.append(named_diagnostic(
            "EVD-SRC-001", layer="claim", claim_ids=[ctx.claim.claim_id], assertion_ids=ids, derivation="grounding_record",
            evidence=[_premise_span(p, symbols) for p, _r in charged][:4] + _claim_spans(ctx),
            message=(f"the point rests on {_names(ids)}, whose {'/'.join(kinds)} label claims a source's or the task's authority, but no check "
                     "verified it in this process (no excerpt, an empty excerpt, or an excerpt no check located): the label alone supports it")))
    if restated:
        ids = [p.id for p, _r in restated]
        kinds = sorted({r.kind for _p, r in restated if r.kind})
        out.append(named_diagnostic(
            "EVD-SRC-001", severity="info", layer="claim", claim_ids=[ctx.claim.claim_id], assertion_ids=ids, derivation="grounding_record",
            evidence=[_premise_span(p, symbols) for p, _r in restated][:4] + _claim_spans(ctx),
            message=(f"the point rests on {_names(ids)}, whose {'/'.join(kinds)} label claims the task's authority with no excerpt; a sentence the "
                     "task asserts holds its words, but no check decided that the task states it (a restatement in other words is not read): "
                     "recorded, not charged; it is still unvalidated in this process")))
    return tuple(out)


def _notation_spelled(p: Any, ctx: Any) -> bool:
    """Whether a task-authority premise's label is the records' notation written in words (``grounding.spells_notation``:
    "x squared is greater than 0" is a run of "x² > 0" read as "x squared greater than 0"; "x is greater than 0" is not). The
    grounding check reads the same rule since repair round 2, so such a label is neither refuted nor named."""
    label = (p.label or "").strip()
    return bool(label) and any(spells_notation(label, src.text[:_MAX_TEXT]) for src in _sources(ctx))


def evd_src_005(ctx: Any) -> Iterable[NamedDiagnostic]:
    """EVD-SRC-005: a needed premise, fact or link, claims the task's authority (task_setting, rubric_rule,
    arithmetic_fact) with no excerpt, and its grounding check found that the task material does not hold it (the figure
    it states, or its own words: ``grounding._words_no_record_holds``). The task record is the one record every task
    has, so the check always runs and the code is shown at warning in every task (re-run review A-EVD-UNCH). A label
    whose missing words are all spelled by the records' mathematical signs ("x squared is greater than 0" for "x² > 0",
    :func:`_notation_spelled`) states what the task states, and is not named."""
    if not _entailed(ctx):
        return ()
    symbols = _symbols(ctx)
    hit = [(p, r) for p, r in _needed_with_role(ctx) if _refuted_task_label(p, r) and not _notation_spelled(p, ctx)]
    if not hit:
        return ()
    ids = [p.id for p, _r in hit]
    kinds = sorted({r.kind for _p, r in hit if r.kind})
    details = [c.detail for c in ctx.translation.grounding_checks if c.verified is False and c.target_id in ids and c.detail]
    return (named_diagnostic(
        "EVD-SRC-005", layer="claim", claim_ids=[ctx.claim.claim_id], assertion_ids=ids, derivation="grounding_record",
        evidence=[_premise_span(p, symbols) for p, _r in hit][:4] + _claim_spans(ctx),
        message=(f"the point rests on {_names(ids)}, whose {'/'.join(kinds)} label claims the task's authority with no excerpt, and the task "
                 "material does not hold it: the label alone supports it" + (f" ({_cut(details[0], 200)})" if details else ""))),)


def evd_src_003(ctx: Any) -> Iterable[NamedDiagnostic]:
    """EVD-SRC-003: the point is ENTAILED, and a needed premise's grounding check failed (the source does not say it).

    A premise whose every failed check located the quotation's words in another form (an initial capital changed for a
    quotation begun mid-sentence, a verse line-break mark, diacritics, a long elision: the grounding check's detail says
    the quotation "differs in form") is not this defect: the source does say it, and the channel names the form difference
    (INT-REQ-010). Its grounding stays unverified, so the result is no more releasable than before (repair round 2,
    ADV2-05)."""
    if not _entailed(ctx):
        return ()
    symbols = _symbols(ctx)
    failed_checks = [c for c in ctx.translation.grounding_checks if c.verified is False]
    failed = {c.target_id for c in failed_checks}
    form_only = {t for t in failed if all(FORM_DIFFERS in (c.detail or "") for c in failed_checks if c.target_id == t)}
    hit = [(p, r) for p, r in _needed_with_role(ctx) if (r.authority == "refuted" or p.id in failed) and not _label_only(p)
           and p.id not in form_only]
    if not hit:
        return ()
    ids = [p.id for p, _r in hit]
    details = [c.detail for c in ctx.translation.grounding_checks if c.verified is False and c.target_id in ids and c.detail]
    return (named_diagnostic(
        "EVD-SRC-003", layer="claim", claim_ids=[ctx.claim.claim_id], assertion_ids=ids, derivation="grounding_record",
        evidence=[_premise_span(p, symbols) for p, _r in hit][:4] + _claim_spans(ctx),
        message=(f"the point is entailed only through {_names(ids)}, whose grounding check failed: the cited source does not say it"
                 + (f" ({_cut(details[0], 200)})" if details else ""))),)


#: Words with which an excerpt can state a rule, a condition, a cause or a closed list in a shape the rule check does not
#: read ("All mammals are warm-blooded" for the whale's instance, "When the bank raises rates, repayments rise", "each"):
#: an excerpt that holds one may state the link, so it is never read as a reference for words alone.
_RULE_SHAPE_WORDS = frozenset("""
if whenever when unless only all every any each both either neither or because since so therefore thus hence cause causes caused
lead leads led means meant implies implied whoever wherever
""".split())


def _side_roots(node: Any, symbols: dict[str, Any]) -> set[str]:
    """The content roots of the meanings of the atoms of one side of a link."""
    names: list[str] = []
    stack = [node]
    while stack:
        n = stack.pop()
        if getattr(n, "op", None) == "var":
            names.append(n.name)
        for attr in ("arg", "left", "right"):
            child = getattr(n, attr, None)
            if child is not None and hasattr(child, "op"):
                stack.append(child)
        stack.extend(a for a in (getattr(n, "args", None) or []) if hasattr(a, "op"))
    return {r for name in names if name in symbols for r in meaning_roots(symbols[name].meaning or "")}


def _cites_words_not_the_link(premise: Any, ctx: Any) -> bool:
    """A link ("if" or "iff") whose every reference a check located, while no check verified its connective (a
    ``relation_in_source`` check, or a stated rule), and whose excerpts can state no link: none holds a word of a rule's
    shape (:data:`_RULE_SHAPE_WORDS`) or words of both its sides (the roots one side's meanings have and the other's lack:
    "The three villages in the valley, Ash, Birch and Cedar" names both sides of 'Ash, Birch and Cedar lost population iff
    all three villages did'). Such excerpts ("Britain", "Explain your answer.", the question the task asks, a source's
    report of the point alone) are references for words, and the link rests on its label alone (repair round 3,
    ADV3-13)."""
    g = premise.grounding
    expr = premise.expr
    while getattr(expr, "op", None) == "not":
        expr = expr.arg
    if g is None or not g.source_refs or getattr(expr, "op", None) not in ("implies", "iff"):
        return False
    symbols = _symbols(ctx)
    left, right = _side_roots(expr.left, symbols), _side_roots(expr.right, symbols)
    only_left, only_right = left - right, right - left
    for r in g.source_refs:
        words = [t.lower() for t in re.findall(r"[A-Za-z]+", r.excerpt or "")]
        held = {lexis_root(t) for t in words}
        if _RULE_SHAPE_WORDS.intersection(words) or (held & only_left and held & only_right):
            return False
    mine = [c for c in ctx.translation.grounding_checks if c.target_id == premise.id]
    located = [c for c in mine if c.method in ("verbatim_match", "normalized_match") and c.verified is True]
    return len(located) >= len(g.source_refs) and not any(c.verified is True and c.method not in ("verbatim_match", "normalized_match") for c in mine)


def _label_only(premise: Any) -> bool:
    """A premise whose grounding cites no reference at all: a source label with nothing a check could locate (a quotation
    with no reference is recorded as refuted; it is an unchecked label, not a source that says otherwise)."""
    g = premise.grounding
    return g is not None and g.kind in TEXT_AUTHORITY_KINDS and not g.source_refs


def _path_premise(path: str, ctx: Any) -> Optional[str]:
    """The premise id a ``problem.premises[<i>].grounding`` path names, else None."""
    m = re.match(r"problem\.premises\[(\d{1,4})\]", path)
    p = ctx.translation.problem
    if m is None or p is None:
        return None
    i = int(m.group(1))
    return p.premises[i].id if i < len(p.premises) else None


def evd_src_004(ctx: Any) -> Iterable[NamedDiagnostic]:
    """EVD-SRC-004 (info): the translation's provider wrote its own ``verified: true`` on a grounding; the flag was discarded,
    because only a check in this process sets it. Every translation, whatever its status."""
    paths = list(ctx.translation.asserted_verified or ())
    if not paths:
        return ()
    ids = [x for x in dict.fromkeys(_path_premise(pth, ctx) for pth in paths) if x]
    return (named_diagnostic(
        "EVD-SRC-004", layer="claim", claim_ids=[ctx.claim.claim_id], assertion_ids=ids, derivation="grounding_record",
        evidence=_claim_spans(ctx),
        message=(f"the translation's provider wrote its own verification flag at {_names(paths)}; the flag was discarded (E505), because only a "
                 "check in this process sets it, so those groundings count only as far as a check verified them")),)


#: Request words that invite the writer's own knowledge beside the supplied material (accuracy round 1, DIFF3-06): "Using
#: Source A and your own knowledge, explain ...".
OWN_KNOWLEDGE_CUES: tuple[str, ...] = ("own knowledge", "your knowledge", "contextual knowledge", "background knowledge", "wider knowledge",
                                       "outside knowledge", "knowledge of your own", "your own understanding", "your understanding")
_OWN_KNOWLEDGE = cue_table(OWN_KNOWLEDGE_CUES)
#: The grounding kind of a fact the writer states from subject knowledge.
_KNOWLEDGE_KIND = "general_knowledge"


def asks_own_knowledge(task_text: Optional[str]) -> bool:
    """Whether the request invites the writer's own knowledge (:data:`OWN_KNOWLEDGE_CUES`), read on its first
    :data:`_MAX_TEXT` characters."""
    return bool(task_text) and has_cue((task_text or "")[:_MAX_TEXT], _OWN_KNOWLEDGE)


def evd_lack_001(ctx: Any) -> Iterable[NamedDiagnostic]:
    """EVD-LACK-001: a needed fact premise claims no source (general knowledge, the specialist's inference, an assumption, no
    grounding) and no check verified it: the point rests on the writer's own unsupported statement.

    An assignment whose every figure is supported is not unsupported, whatever its label (repair round 3,
    V3-E2E-NEW-EVD-FALSE-WARNINGS): a record states the figure for the premise's subject (P₀ = 250 when the table gives
    January's 250), or the answer's working derives it (:func:`.grounding.assignment_support`: "(2.00 − 1.60) ÷ 1.60 × 100
    = 25.00%", "k = (1/10) ln(8.04 × 10⁸), which is 2.050511…"). Its grounding is not verified by that reading, so the
    result is no more releasable than before; only the name goes."""
    if not _entailed(ctx):
        return ()
    symbols = _symbols(ctx)
    hit = [(p, r) for p, r in _needed_with_role(ctx, "fact") if (r.kind is None or r.kind in WRITER_KINDS) and r.authority in ("writer_own", "unverified")
           and not _figures_supported(ctx, p, symbols)]
    if not hit:
        return ()
    invited: list[tuple[Any, Any]] = []
    if asks_own_knowledge(ctx.task_text):
        # the request invites the writer's own knowledge: a fact stated from it is what the request asks for, so it is recorded
        # at info, capped as outside the request's source-bound scope (it still blocks release: nothing checked it), never
        # named at warning (accuracy round 1, DIFF3-06); a fact of another kind (the writer's own inference) stays a warning
        invited = [(p, r) for p, r in hit if r.kind == _KNOWLEDGE_KIND]
        hit = [(p, r) for p, r in hit if r.kind != _KNOWLEDGE_KIND]
    out: list[NamedDiagnostic] = []
    if hit:
        ids = [p.id for p, _r in hit]
        out.append(named_diagnostic(
            "EVD-LACK-001", layer="claim", claim_ids=[ctx.claim.claim_id], assertion_ids=ids, derivation="grounding_record",
            evidence=[_premise_span(p, symbols) for p, _r in hit][:4] + _claim_spans(ctx),
            message=(f"the point rests on {_names(ids)} ({'; '.join(_cut(p.label or p.id, 90) for p, _r in hit[:3])}), which cites no source, and no "
                     "check verified it in this process: nothing in the supplied texts or the task supports it")))
    if invited:
        ids = [p.id for p, _r in invited]
        d = named_diagnostic(
            "EVD-LACK-001", layer="claim", claim_ids=[ctx.claim.claim_id], assertion_ids=ids, derivation="grounding_record",
            evidence=[_premise_span(p, symbols) for p, _r in invited][:4] + _claim_spans(ctx),
            message=(f"the point rests on {_names(ids)} ({'; '.join(_cut(p.label or p.id, 90) for p, _r in invited[:3])}), stated from the writer's own "
                     "knowledge, which the request invites; no check verified it in this process"))
        out.extend(cap([d], "info", "not_source_bound"))
    return tuple(out)


def _answer_texts(ctx: Any) -> list[str]:
    """The answer's own texts: the claim, its supporting claims and the whole response (the working a figure may come from)."""
    texts = [ctx.claim.claim_text, *(c.claim_text for c in ctx.supporting)]
    if ctx.report is not None and getattr(ctx.report, "original_response", None):
        texts.append(ctx.report.original_response)
    return [t for t in texts if t]


def _figures_supported(ctx: Any, p: Any, symbols: dict[str, Any]) -> bool:
    """Whether every figure of an assignment premise is supported: the translation's own reading finds it calculated over
    stated figures, or a record states it for the premise's subject, or the answer's working derives it. False for a
    premise that is no assignment, or whose figures are all trivial."""
    from .diag_figures import assignment_support
    from .relations import assignment_parts
    if not assignment_parts(p.expr):
        return False
    from .quantities import figures_in
    if _calculated_over_stated(ctx, p.id, [f for s in _sources(ctx) for f in figures_in(s)]):
        return True
    support = assignment_support(p.expr, symbols, p.label, _sources(ctx), _answer_texts(ctx))
    return bool(support) and all(s.status in ("stated", "answer_stated", "worked") and s.same_subject for s in support)


def _sources(ctx: Any) -> list[Any]:
    """The records a figure may occur in: every supplied text of the report and the task record."""
    from .quantities import SourceText
    out = []
    if ctx.report is not None:
        out += [SourceText("supplied_text", t.document_id, t.text) for t in ctx.report.supplied_texts]
    if ctx.task is not None:
        out.append(SourceText("task", ctx.task.task_id, ctx.task.text))
    return out


def _memory_labelled(ctx: Any) -> bool:
    from ..adapters.markdown import is_memory_label
    texts = [ctx.claim.claim_text, *(c.claim_text for c in ctx.supporting)]
    if ctx.report is not None:  # a from-memory note of the report (a label sentence of its own) covers its figures
        texts += [c.claim_text for c in ctx.report.claims if c.claim_role == "other"]
    return any(is_memory_label(t[:4000]) for t in texts if t)


def _reading_text(ctx: Any, fr: Any) -> Optional[str]:
    if fr.source_kind == "claim":
        return ctx.claim.claim_text
    if fr.source_kind == "supporting_claim":
        return next((c.claim_text for c in ctx.supporting if c.claim_id == fr.source_id), None)
    return None


def _calculated_over_stated(ctx: Any, premise_id: str, figures: Sequence[Any]) -> bool:
    """Whether the figure of ``premise_id`` is the result of a written calculation over figures the records state: its
    reading carries the calculation's value (or the convention of written calculation), and every operand written before the
    result in its sentence is stated by a supplied text or the task record, is trivial (0, 1, 10, 100, 1000), or is itself
    the result of an earlier step ("120 × 8 = 960; 960 − 900 = 60"). A result computed from an unstated operand is the
    answer's own figure."""
    from .quantities import TRIVIAL_VALUES, literal_matches
    readings = [fr for fr in ctx.translation.figure_readings if premise_id in fr.assertion_ids and (fr.calculated is not None or fr.by_convention)]
    if not readings:
        return False
    for fr in readings:
        text = _reading_text(ctx, fr)
        if text is None or fr.start is None:
            continue  # the calculation is not located: its operands cannot be read, so it counts as written
        head = text[:fr.start]
        stop = max(head.rfind(". "), head.rfind("! "), head.rfind("? "), head.rfind("\n"))
        span = _masked(head[stop + 1:])
        spans = _tokens(span)
        for k, (a, _b, tok) in enumerate(spans):
            if not _is_number(tok) or _is_year(tok):
                continue
            before = span[spans[k - 1][1]:a] if k else span[:a]
            if "=" in before or "≈" in before:
                continue  # the result of an earlier step of the same calculation
            value = _number_value(tok)
            if value is None or abs(value) in TRIVIAL_VALUES:
                continue
            matches, _why = literal_matches(value, figures)
            if not matches:
                return False
    return True


def evd_fig_001(ctx: Any) -> Iterable[NamedDiagnostic]:
    """EVD-FIG-001: a needed assignment premise whose figure the ANSWER writes, that occurs in no supplied text and not in
    the task record, that is no result of the answer's written working over stated figures, and whose claim carries no
    from-memory label: a figure the answer introduces.

    The figure is read as the answer writes it (repair round 3, V3-E2E-NEW-EVD-FALSE-WARNINGS;
    :func:`.grounding.assignment_support`): a bound is stated when it is an end of the interval a record's figure states at
    its written precision ("≈ 1.55" states [1.545, 1.555)); an interval stands for the answer's figure it lies in ("about
    1.26"), which the records may state; a worked result of the answer's working is no introduced figure ("(2.00 − 1.60) ÷
    1.60 × 100 = 25.00%", "eᵏ = e^(2.050511…) = 7.77187…", a chain continued on the next line), when its operands are
    stated, trivial, results of earlier working or truncated computed values ("0.693147…"); a year the symbol's meaning
    names as a date identifies a time and states no quantity (an unsupported date is EVD-LACK-001's); and a figure no text
    of the answer writes is the translation's, not the answer's (its fidelity is the review's)."""
    if not _entailed(ctx):
        return ()
    from .diag_figures import assignment_support
    from .quantities import figures_in
    from .relations import assignment_parts
    symbols = _symbols(ctx)
    sources = _sources(ctx)
    figures = [f for s in sources for f in figures_in(s)]
    answer = _answer_texts(ctx)
    hit: list[tuple[Any, list[str]]] = []
    for p, r in _needed_with_role(ctx, "fact"):
        if r.authority == "established":
            continue
        parts = assignment_parts(p.expr)
        if not parts or _calculated_over_stated(ctx, p.id, figures):
            continue
        support = assignment_support(p.expr, symbols, p.label, sources, answer) or []
        missing = ["/".join(s.written) + (f" (written {s.answer_figure!r})" if s.answer_figure and s.answer_figure not in s.written else "")
                   for s in support if s.status == "introduced"]
        if missing:
            hit.append((p, missing))
    if not hit or _memory_labelled(ctx):
        return ()
    ids = [p.id for p, _m in hit]
    written = [w for _p, m in hit for w in m]
    where = "no supplied text and not the task record" if sources else "no supplied text (none was supplied) and no task record"
    return (named_diagnostic(
        "EVD-FIG-001", layer="claim", claim_ids=[ctx.claim.claim_id], assertion_ids=ids, derivation="source_text",
        evidence=[_premise_span(p, symbols) for p, _m in hit][:4] + _claim_spans(ctx),
        message=(f"the point needs the figure(s) {_names(written)} of {_names(ids)}, which {where} states; no written calculation over stated "
                 "figures gives them and no from-memory label covers them: the answer introduces them")),)


def _literal_value(node: Any) -> Optional[Fraction]:
    """The exact value of an IR literal node (int, real, decimal or fraction text; a negation of one), else None."""
    neg = False
    while getattr(node, "op", None) == "neg":
        neg, node = not neg, node.arg
    if getattr(node, "op", None) not in ("int", "real"):
        return None
    try:
        v = Fraction(node.value)
    except (ValueError, ZeroDivisionError):
        return None
    return -v if neg else v


def _written(node: Any) -> str:
    neg = ""
    while getattr(node, "op", None) == "neg":
        neg, node = ("" if neg else "-"), node.arg
    return neg + str(getattr(node, "value", "?"))


def _authority_cue(text: str, *, supplied: bool, authors: frozenset[str] = frozenset()) -> Optional[tuple[int, int]]:
    """The character span of an unattributed authority or data cue in ``text`` (module docstring), else None. A cue right
    after a definite determiner names the supplied material when the task supplies texts ("the data show"), and a named
    author with a year is an attributed source."""
    if not text:
        return None
    spans = _tokens(text)
    toks = tuple(t for _s, _e, t in spans)
    for i, cue in find_cues(toks, _AUTHORITY_FIXED):
        return spans[i][0], spans[i + len(cue) - 1][1]
    for i, cue in find_cues(toks, _AUTHORITY_CUES):
        before = toks[max(0, i - 3):i]
        if supplied and any(t in _DEFINITE for t in before):
            continue
        a, b = spans[i][0], spans[i + len(cue) - 1][1]
        if _NAMED_AUTHOR_YEAR_RE.search(text[max(0, a - 80):a]):
            continue
        return a, b
    for i, cue in find_cues(toks, _AUTHORITY_PERSON_CUES):
        a, b = spans[i][0], spans[i + len(cue) - 1][1]
        names = {t for t in toks[i + 1:i + len(cue)] if t not in ("has", "have")} - set(cue)
        if names & authors:
            continue  # the person is a supplied text's author: an attributed, checkable source
        if _NAMED_AUTHOR_YEAR_RE.search(text[a:min(len(text), b + 12)]) or re.search(r"\((?:1[0-9]{3}|20[0-9]{2})\)", text[a:min(len(text), b + 12)]):
            continue  # a named author with a year is an attributed source
        return a, b
    return None


#: How far after an authority cue a quotation it introduces may begin and end (characters).
_QUOTED_AUTHORITY_REACH = 600


def evd_auth_001(ctx: Any) -> Iterable[NamedDiagnostic]:
    """EVD-AUTH-001: a needed premise that no check verified leans on an unattributed authority or data cue, in its own words
    (label, symbol meanings) or in the claim or supporting sentence that states it. A cue in a statement that introduces a
    quotation located in a supplied text names the supplied text's authority, which is attributed (accuracy round 2)."""
    if not _entailed(ctx):
        return ()
    symbols = _symbols(ctx)
    supplied = bool(ctx.report is not None and ctx.report.supplied_texts)
    authors = frozenset(t for d in (ctx.report.supplied_texts if ctx.report is not None else ())
                        for t in (tok for _s, _e, tok in token_spans(" ".join(x for x in (getattr(d, "author", None) or "", getattr(d, "title", None) or "") if x)))
                        if len(t) > 2)
    statements = [("claim", ctx.claim.claim_id, ctx.claim.claim_text)] + [("supporting_claim", c.claim_id, c.claim_text) for c in ctx.supporting]
    read: list[tuple[str, str, str, Optional[tuple[int, int]], set[str]]] = []  # each statement masked and read once, on first need
    docs = {t.document_id: t for t in ctx.report.supplied_texts} if supplied else {}

    def statement_cues() -> list[tuple[str, str, str, Optional[tuple[int, int]], set[str]]]:
        if not read:
            for kind, sid, text in statements:
                masked = _masked(text)
                cue = _authority_cue(masked, supplied=supplied, authors=authors)
                if cue is not None and docs and _located_quotation(text[cue[1]:cue[1] + _QUOTED_AUTHORITY_REACH], docs):
                    # the cue introduces a quotation located in a supplied text ('Historian M argues that "the Crash drove German
                    # unemployment up"' quoting Source A): the authority is the supplied text's, attributed and checked (accuracy
                    # round 2, a false alarm on the quoted bridges of DIFF3-02's probes)
                    cue = None
                read.append((kind, sid, text, cue, _stems(masked)))
        return read
    hit: list[tuple[Any, EvidenceSpan]] = []
    for p, r in _needed_with_role(ctx):
        if r.authority == "established":
            continue
        gloss = _gloss(p, symbols)
        cue = _authority_cue(gloss, supplied=supplied, authors=authors)
        if cue is not None:
            hit.append((p, _span("premise_label", p.id, gloss[cue[0]:cue[1]], None, None)))
            continue
        mine = _stems(gloss)
        for kind, sid, text, cue, stems in statement_cues():
            if cue is not None and len(mine & stems) >= 2:  # the statement states this premise, and leans on the cue
                hit.append((p, _span(kind, sid, text[cue[0]:cue[1]], cue[0], cue[1])))
                break
    if not hit:
        return ()
    ids = [p.id for p, _s in hit]
    return (named_diagnostic(
        "EVD-AUTH-001", layer="claim", claim_ids=[ctx.claim.claim_id], assertion_ids=ids, derivation="ir_glosses",
        evidence=[s for _p, s in hit][:4] + _claim_spans(ctx),
        message=(f"the point rests on {_names(ids)}, which leans on an unattributed authority or data ('{_cut(hit[0][1].text, 80)}'), names no "
                 "checkable source, and no check verified it: the appeal cannot be checked")),)


#: Words between two years that make them the two ends of a period ("2010 to 2020", "2010 until 2020").
_PERIOD_JOINERS = frozenset({"to", "until", "till", "through", "and"})


def _periods(text: str, latest: Optional[int] = None) -> list[tuple[int, int, int, int]]:
    """``(first year, last year, start, end)`` of every period ``text`` names: "between Y1 and Y2", "from Y1 to Y2",
    "Y1 to Y2" ("over the period 2010 to 2020"), "Y1 until Y2", "Y1-Y2" (a hyphen or dash between the years), with Y1 <
    Y2; and "since Y1", which runs to ``latest`` (the latest year the supplied data give) when that is later (repair
    round 1, re-run review ADV-03: the token after "2010" in "2010 to 2020" is "to", so that branch never matched)."""
    spans = _tokens(text)
    out: list[tuple[int, int, int, int]] = []
    for k, (s, e, t) in enumerate(spans):
        if not _is_year(t):
            continue
        if k + 2 < len(spans) and spans[k + 1][2] in _PERIOD_JOINERS and _is_year(spans[k + 2][2]) \
                and not (spans[k + 1][2] == "and" and not (k >= 1 and spans[k - 1][2] == "between")):
            y1, y2 = int(t), int(spans[k + 2][2])
            if y1 < y2:
                start = spans[k - 1][0] if k >= 1 and spans[k - 1][2] in ("between", "from") else s
                out.append((y1, y2, start, spans[k + 2][1]))
        elif k + 1 < len(spans) and _is_year(spans[k + 1][2]) and text[e:spans[k + 1][0]].strip() in ("-", "–", "—"):
            y1, y2 = int(t), int(spans[k + 1][2])
            if y1 < y2:
                out.append((y1, y2, s, spans[k + 1][1]))
        elif k >= 1 and spans[k - 1][2] == "since" and latest is not None and int(t) < latest:
            out.append((int(t), latest, spans[k - 1][0], e))
    return out


#: Words after a year that end its pairing with a later figure ("fell from 42% in 2014 to 18% in 2024": 18 is 2024's).
_NOT_PAIRED_AFTER_YEAR = frozenset({"to", "from", "until", "till", "and", "than", "versus", "vs", "compared", "against"})


def _year_values(text: str) -> dict[int, set[Fraction]]:
    """``{year: values}`` a text pairs with years: a figure right after a year, with only punctuation between them ("2019:
    5.0%", "2020 - 8.0"); the first figure after a year in its clause, before any other year, within eight tokens and with
    no "to", "from", "and" or "than" between them ("In 2010 the population was 610"); and a figure right before "in
    <year>" ("610 in 2010")."""
    spans = _tokens(text)
    out: dict[int, set[Fraction]] = {}
    for k, (_s, e, t) in enumerate(spans):
        if not _is_year(t):
            continue
        for j in range(k + 1, min(len(spans), k + 9)):
            s2, _e2, t2 = spans[j]
            gap = text[spans[j - 1][1]:s2]
            if any(ch in ".;!?\n" for ch in gap) or _is_year(t2) or t2 in _NOT_PAIRED_AFTER_YEAR:
                break
            if _is_number(t2):
                v = _number_value(t2)
                if v is not None and (j == k + 1 or not any(ch.isdigit() for ch in text[e:s2])):
                    out.setdefault(int(t), set()).add(v)
                break
    for k in range(len(spans) - 2):
        t, nxt, y = spans[k][2], spans[k + 1][2], spans[k + 2][2]
        if _is_number(t) and not _is_year(t) and nxt == "in" and _is_year(y):
            v = _number_value(t)
            if v is not None:
                out.setdefault(int(y), set()).add(v)
    return out


def _years_in(text: str) -> set[int]:
    return {int(t) for _s, _e, t in _tokens(text) if _is_year(t)}


# ----------------------------------------------------------------------------------------------- months (repair round 2)
# A trend over months of one year ("rose in the first half of the year", "between January and June") is read like one over
# years: the months are time keys 10001 to 10012 (never a year), so the same period, value and end rules apply
# (NAME-CHERRY-GENERIC: a January-March sample read as the January-June trend).
_MONTH_KEY_BASE = 10_000
_MONTH_NAMES = {name: k for k, names in enumerate((("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"), ("may",),
                                                    ("june", "jun"), ("july", "jul"), ("august", "aug"), ("september", "sep", "sept"),
                                                    ("october", "oct"), ("november", "nov"), ("december", "dec")), start=1) for name in names}
#: Named parts of a year, as month ranges.
_YEAR_PARTS = {("first", "half"): (1, 6), ("second", "half"): (7, 12), ("first", "quarter"): (1, 3), ("second", "quarter"): (4, 6),
               ("third", "quarter"): (7, 9), ("fourth", "quarter"): (10, 12), ("last", "quarter"): (10, 12)}
_COUNT_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}


def _month_at(text: str, spans: Sequence[tuple[int, int, str]], k: int) -> Optional[int]:
    """The month the token ``k`` names (1 to 12), else None. Only a name written with a capital is a month: "may", "march",
    "mar" and "dec" are also ordinary words."""
    t = spans[k][2]
    m = _MONTH_NAMES.get(t)
    if m is None or not text[spans[k][0]:spans[k][0] + 1].isupper():
        return None
    return m


def _month_keys_in(text: str) -> set[int]:
    spans = _tokens(text)
    return {_MONTH_KEY_BASE + m for k in range(len(spans)) if (m := _month_at(text, spans, k)) is not None}


def _month_periods(text: str) -> list[tuple[int, int, int, int]]:
    """``(first key, last key, start, end)`` of the month periods ``text`` names: "between January and June", "from January to
    June", "January to June", "January-June", "the first half of the year" (January to June), "the first quarter", "the first
    six months"."""
    spans = _tokens(text)
    out: list[tuple[int, int, int, int]] = []
    for k in range(len(spans)):
        m1 = _month_at(text, spans, k)
        if m1 is not None:
            m2 = None
            end = 0
            if k + 2 < len(spans) and spans[k + 1][2] in _PERIOD_JOINERS and not (spans[k + 1][2] == "and" and not (k >= 1 and spans[k - 1][2] == "between")):
                m2, end = _month_at(text, spans, k + 2), spans[k + 2][1]
            elif k + 1 < len(spans) and text[spans[k][1]:spans[k + 1][0]].strip() in ("-", "–", "—"):
                m2, end = _month_at(text, spans, k + 1), spans[k + 1][1]
            if m2 is not None and m1 < m2:
                start = spans[k - 1][0] if k >= 1 and spans[k - 1][2] in ("between", "from") else spans[k][0]
                out.append((_MONTH_KEY_BASE + m1, _MONTH_KEY_BASE + m2, start, end))
            continue
        pair = (spans[k][2], spans[k + 1][2]) if k + 1 < len(spans) else None
        if pair in _YEAR_PARTS and k + 3 < len(spans) and spans[k + 2][2] == "of":
            a, b = _YEAR_PARTS[pair]
            if spans[k + 3][2] == "the" and k + 4 < len(spans) and spans[k + 4][2] == "year":  # "the first half of the year"
                out.append((_MONTH_KEY_BASE + a, _MONTH_KEY_BASE + b, spans[k][0], spans[k + 4][1]))
            elif _is_year(spans[k + 3][2]):                                                   # "the first half of 2021"
                out.append((_MONTH_KEY_BASE + a, _MONTH_KEY_BASE + b, spans[k][0], spans[k + 3][1]))
        elif spans[k][2] == "first" and k + 2 < len(spans) and spans[k + 2][2] == "months" and spans[k + 1][2] in _COUNT_WORDS:
            out.append((_MONTH_KEY_BASE + 1, _MONTH_KEY_BASE + _COUNT_WORDS[spans[k + 1][2]], spans[k][0], spans[k + 2][1]))
    return out


def _month_values(text: str) -> dict[int, set[Fraction]]:
    """``{month key: values}`` a text pairs with months, by the rules :func:`_year_values` applies to years ("January: 120",
    "In March the figure was 95", "120 in January")."""
    spans = _tokens(text)
    out: dict[int, set[Fraction]] = {}
    for k in range(len(spans)):
        m = _month_at(text, spans, k)
        if m is None:
            continue
        for j in range(k + 1, min(len(spans), k + 9)):
            s2, _e2, t2 = spans[j]
            gap = text[spans[j - 1][1]:s2]
            if any(ch in ".;!?\n" for ch in gap) or _month_at(text, spans, j) is not None or t2 in _NOT_PAIRED_AFTER_YEAR:
                break
            if _is_number(t2) and not _is_year(t2):
                v = _number_value(t2)
                if v is not None:
                    out.setdefault(_MONTH_KEY_BASE + m, set()).add(v)
                break
        if k >= 2 and spans[k - 1][2] == "in" and _is_number(spans[k - 2][2]) and not _is_year(spans[k - 2][2]):
            v = _number_value(spans[k - 2][2])
            if v is not None:
                out.setdefault(_MONTH_KEY_BASE + m, set()).add(v)
    return out


def _key_text(key: int) -> str:
    if key > _MONTH_KEY_BASE:
        return ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
                "December")[key - _MONTH_KEY_BASE - 1]
    return str(key)


def _direction(text: str) -> Optional[str]:
    """``falling`` or ``rising``: the one direction ``text`` states, else None."""
    words = {t for _s, _e, t in _tokens(_masked(text))}
    falling, rising = bool(words & FALLING_WORDS), bool(words & RISING_WORDS)
    if falling == rising:
        return None
    return "falling" if falling else "rising"


def evd_cherry_001(ctx: Any) -> Iterable[NamedDiagnostic]:
    """EVD-CHERRY-001: the point names a period, a supplied text gives one value for each of its end years, the encoding's
    data premises or the evidence claim use only years inside the period, and with the end values the point's stated
    direction fails, or (repair round 3) the years used stop before the period's end and the period's end value runs back
    against the direction from the last year used (the window's rise is not the period's). The omitted values are named.
    Any decided result."""
    if not _decided(ctx) or ctx.report is None or not ctx.report.supplied_texts:
        return ()
    text = ctx.claim.claim_text
    direction = _direction(text)
    if direction is None:
        fold = _stated_fold(text)  # "more than quintupled", "rose fivefold": the fold's direction
        direction = None if fold is None else ("rising" if fold[0] > 1 else "falling")
    if direction is None:
        return ()
    symbols = _symbols(ctx)
    premises = _premise_map(ctx)
    roles = _roles(ctx)
    data_years: set[int] = set()
    for pid, p in premises.items():
        r = roles.get(pid)
        if r is not None and r.role == "fact":
            data_years |= _years_in(_gloss(p, symbols)) | _month_keys_in(_gloss(p, symbols))
    evidence_years: set[int] = set()
    for c in ctx.supporting:
        evidence_years |= _years_in(c.claim_text) | _month_keys_in(c.claim_text)
    tables = [(doc, {**_year_values(doc.text), **_month_values(doc.text)}) for doc in ctx.report.supplied_texts]
    latest = max((y for _d, pairs in tables for y in pairs if y < _MONTH_KEY_BASE), default=None)
    for y1, y2, a, b in _periods(_masked(text), latest) + _month_periods(_masked(text)):
        def own_kind(years: set[int]) -> set[int]:
            # the time points of the period's own kind: years for a period of years, months for a period of months
            return {y for y in years if (y > _MONTH_KEY_BASE) == (y1 > _MONTH_KEY_BASE)}

        def leaves_an_end_out(years: set[int]) -> bool:
            # every year used lies in the period, and at least one of its two end years is not used (2012 and 2013 for a
            # 2012-2020 trend leave 2020 out): a sub-period, read as the period's trend (re-run review A-EVD-CHERRY)
            years = own_kind(years)
            return bool(years) and all(y1 <= y <= y2 for y in years) and not (y1 in years and y2 in years)
        if not (leaves_an_end_out(data_years) or leaves_an_end_out(evidence_years)):
            continue
        for doc, pairs in tables:
            v1, v2 = pairs.get(y1), pairs.get(y2)
            if not v1 or not v2 or len(v1) != 1 or len(v2) != 1:
                continue
            first, last = next(iter(v1)), next(iter(v2))
            fails = (direction == "falling" and not last < first) or (direction == "rising" and not last > first)
            used = sorted(own_kind(data_years if leaves_an_end_out(data_years) else evidence_years))
            if not fails:
                # the window the argument uses stops before the period's end, and the data after it run back against the point's
                # direction: a rise read from 2012-2013 (3.4 to 5.0) for "recovered over 2012-2020" when the figure falls back to
                # 3.8 by 2020 (repair round 3, V3-CHERRY-ESS-UNNAMED). A window whose trend the later data continue is no
                # cherry-pick.
                cut = max(used) if used and y2 not in used else None
                vc = pairs.get(cut) if cut is not None else None
                if not vc or len(vc) != 1:
                    continue
                at_cut = next(iter(vc))
                if not ((direction == "rising" and last < at_cut) or (direction == "falling" and last > at_cut)):
                    continue
                kc, k1, k2 = _key_text(cut), _key_text(y1), _key_text(y2)
                unit = "months" if y1 > _MONTH_KEY_BASE else "years"
                back = "falls back" if direction == "rising" else "climbs back"
                return (named_diagnostic(
                    "EVD-CHERRY-001", layer="claim", claim_ids=[ctx.claim.claim_id], assertion_ids=[pid for pid, r in roles.items() if r.role == "fact"][:16],
                    derivation="source_text",
                    evidence=[_span("claim", ctx.claim.claim_id, text[a:b], a, b),
                              _span("supplied_text", doc.document_id, f"{kc}: {_fmt(at_cut)}; {k2}: {_fmt(last)}")],
                    message=(f"the point states a {direction} trend over {k1}-{k2} from the {unit} {', '.join(_key_text(u) for u in used)} only; "
                             f"{doc.document_id} gives {_fmt(at_cut)} for {kc} and {_fmt(last)} for {k2}: after the window the argument uses, the "
                             f"figure {back}, which the argument leaves out")),)
            what = "rose" if last > first else "fell" if last < first else "did not change"
            k1, k2 = _key_text(y1), _key_text(y2)
            unit = "months" if y1 > _MONTH_KEY_BASE else "years"
            return (named_diagnostic(
                "EVD-CHERRY-001", layer="claim", claim_ids=[ctx.claim.claim_id], assertion_ids=[pid for pid, r in roles.items() if r.role == "fact"][:16],
                derivation="source_text",
                evidence=[_span("claim", ctx.claim.claim_id, text[a:b], a, b), _span("supplied_text", doc.document_id, f"{k1}: {_fmt(first)}; {k2}: {_fmt(last)}")],
                message=(f"the point states a {direction} trend over {k1}-{k2} from the {unit} {', '.join(_key_text(u) for u in used)} "
                         f"only; {doc.document_id} gives {_fmt(first)} for {k1} and {_fmt(last)} for {k2}, the period's own end values, which the "
                         f"argument leaves out: over {k1}-{k2} the figure {what}")),)
    return _cherry_beyond(ctx, text, direction, data_years | evidence_years, tables, roles)


#: A point's anaphor for the period the request names ("over the decade", "over the period"): the request's period is the
#: point's (EVD-CHERRY-001, repair round 2).
_PERIOD_ANAPHOR_RE = re.compile(r"\b(?:over|during|across|throughout|in)\s+(?:the|this|that)\s+(?:whole\s+|entire\s+)?(?:decade|period|years|time|"
                                r"(?:\w+\s+)?years?)\b", re.IGNORECASE)
#: A point that states a trend still going on ("is recovering", "are rising", "continues to fall", "still growing").
_PRESENT_TREND_RE = re.compile(r"\b(?:is|are|has\s+been|have\s+been|keeps|still)\s+(?:now\s+|clearly\s+|steadily\s+)?(\w+ing)\b|\bcontinues?\s+to\s+(\w+)\b",
                               re.IGNORECASE)
#: Fold words a point may state of a period: (word, factor, sense) with sense '=' (about the factor), '>' (more than) read
#: from "more than" before it.
_FOLD_WORDS = {"doubled": Fraction(2), "tripled": Fraction(3), "trebled": Fraction(3), "quadrupled": Fraction(4), "quintupled": Fraction(5),
               "sextupled": Fraction(6), "halved": Fraction(1, 2)}
_FOLD_NUMBERS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twenty": 20, "hundred": 100}
_FOLD_RE = re.compile(r"\b(?:(?P<w>two|three|four|five|six|seven|eight|nine|ten|twenty|hundred)|(?P<n>\d{1,3}))[- ]?fold\b")


def _stated_fold(text: str) -> Optional[tuple[Fraction, bool]]:
    """``(factor, more_than)`` a point states ("more than quadrupled": (4, True); "rose fivefold": (5, False)), else None."""
    low = " ".join(_masked(text).lower().split())
    for word, factor in _FOLD_WORDS.items():
        k = low.find(word)
        if k >= 0:
            return factor, bool(re.search(r"(?:more\s+than|over|at\s+least)\s+$", low[:k]))
    m = _FOLD_RE.search(low)
    if m is not None:
        n = _FOLD_NUMBERS[m.group("w")] if m.group("w") else int(m.group("n"))
        if n >= 2 and not re.search(r"\b(?:fell|dropped|declined|decreased|shrank|cut)\b", low[:m.start()]):
            return Fraction(n), bool(re.search(r"(?:more\s+than|over|at\s+least)\s+$", low[:m.start()]))
    return None


def _cherry_beyond(ctx: Any, text: str, direction: str, used: set[int], tables: list, roles: dict) -> Iterable[NamedDiagnostic]:
    """EVD-CHERRY-001 for a point with no period of its own (repair round 2, holdout2 cherry class): (a) the point names the
    request's period by an anaphor ("over the decade") and the argument uses only part of it, leaving out an end the data give,
    and with the end values its direction or its stated fold ("more than quadrupled") fails; (b) the point states a trend still
    going on ("is recovering") from years that stop before the latest year the data give, and from the last year used to the
    latest one the figure moves the other way."""
    years = {y for y in used if y < _MONTH_KEY_BASE}
    if not years or _years_in(text):
        return ()  # a point that names years of its own states its own period (the rules above read it)
    # the point's main clause: a concessive or contrasting clause speaks of something else ('..., although prices were still rising')
    main = re.split(r"\b(?:although|though|but|while|whereas|even\s+though|despite)\b", _masked(text), maxsplit=1, flags=re.IGNORECASE)[0]
    period = None
    if _PERIOD_ANAPHOR_RE.search(main) and getattr(ctx, "task", None) is not None:
        found = _periods(ctx.task.text[:_MAX_TEXT])
        if len({(y1, y2) for y1, y2, _a, _b in found}) == 1:
            period = (found[0][0], found[0][1])
    facts = [pid for pid, r in roles.items() if r.role == "fact"][:16]
    for doc, pairs in tables:
        series = sorted(y for y in pairs if y < _MONTH_KEY_BASE and len(pairs[y]) == 1)
        if len(series) < 3:
            continue
        if period is not None:
            y1, y2 = period
            if not (all(y1 <= y <= y2 for y in years) and not (y1 in years and y2 in years)) or y1 not in pairs or y2 not in pairs:
                continue
            first, last = next(iter(pairs[y1])), next(iter(pairs[y2]))
            fold = _stated_fold(text)
            if fold is not None and first:
                factor, more = fold
                ratio = last / first
                fails = (ratio <= factor if more else not (factor * Fraction(9, 10) <= ratio <= factor * Fraction(11, 10))) if factor > 1 else \
                        (ratio >= factor if more else not (factor * Fraction(9, 10) <= ratio <= factor * Fraction(11, 10)))
                claim = f"{'more than ' if more else ''}a {float(factor):g}-fold change"
            else:
                fails = (direction == "falling" and not last < first) or (direction == "rising" and not last > first)
                claim = f"a {direction} trend"
            if not fails:
                continue
            return (named_diagnostic(
                "EVD-CHERRY-001", layer="claim", claim_ids=[ctx.claim.claim_id], assertion_ids=facts, derivation="source_text",
                evidence=[_span("claim", ctx.claim.claim_id, text[:200], 0, min(len(text), 200)),
                          _span("supplied_text", doc.document_id, f"{y1}: {_fmt(first)}; {y2}: {_fmt(last)}")],
                message=(f"the point states {claim} over the request's period {y1}-{y2} from the years {', '.join(str(y) for y in sorted(years))} only; "
                         f"{doc.document_id} gives {_fmt(first)} for {y1} and {_fmt(last)} for {y2}, the period's own end values, which the argument "
                         f"leaves out: over {y1}-{y2} the change is a factor of {float(last / first) if first else 0:.3g}")),)
        m = _PRESENT_TREND_RE.search(main)
        if m is None:
            continue
        verb = (m.group(1) or m.group(2) or "").lower()
        if verb not in RISING_WORDS and verb not in FALLING_WORDS and not verb.endswith("ing"):
            continue
        latest, last_used = series[-1], max(years)
        if last_used >= latest or last_used not in pairs:
            continue
        a, b = next(iter(pairs[last_used])), next(iter(pairs[latest]))
        fails = (direction == "rising" and not b > a) or (direction == "falling" and not b < a)
        if not fails:
            continue
        what = "rose" if b > a else "fell" if b < a else "did not change"
        return (named_diagnostic(
            "EVD-CHERRY-001", layer="claim", claim_ids=[ctx.claim.claim_id], assertion_ids=facts, derivation="source_text",
            evidence=[_span("claim", ctx.claim.claim_id, text[:200], 0, min(len(text), 200)),
                      _span("supplied_text", doc.document_id, f"{last_used}: {_fmt(a)}; {latest}: {_fmt(b)}")],
            message=(f"the point states a {direction} trend that is still going on ('{m.group(0)}') from the years "
                     f"{', '.join(str(y) for y in sorted(years))} only; {doc.document_id} runs to {latest}, and from {last_used} to {latest} the "
                     f"figure {what} ({_fmt(a)} to {_fmt(b)}), which the argument leaves out")),)
    return ()


def _fmt(v: Fraction) -> str:
    if v.denominator == 1:
        return str(v.numerator)
    s = f"{float(v):.6g}"
    return s


#: Claim-layer evidence rules, run in this order after the argument rules.
RULES: tuple[Callable[..., Iterable[NamedDiagnostic]], ...] = (
    evd_src_003, evd_src_005, evd_src_001, evd_auth_001, evd_fig_001, evd_cherry_001, evd_lack_001, evd_src_004)


# ----------------------------------------------------------------------------------------------- report rules

def _paragraph_sections(report: Any) -> dict[str, str]:
    """``{claim id: the text of its answer section}``: the paragraph (blank-line block) of the answer holding the claim's text,
    or the whole answer when the claim is not located in one paragraph or the answer has one paragraph only."""
    answer = (getattr(report, "original_response", "") or "")[:_MAX_TEXT]
    blocks = [b for b in re.split(r"\n\s*\n", answer) if b.strip()]
    out: dict[str, str] = {}
    for c in list(report.claims)[:_MAX_CLAIMS]:
        text = (c.claim_text or "").strip()
        if len(blocks) > 1 and text:
            holder = next((b for b in blocks if text[:200] in b), None)
            out[c.claim_id] = holder if holder is not None else answer
        else:
            out[c.claim_id] = answer
    return out


def _located_quotation(section: str, docs: dict[str, Any]) -> bool:
    """Whether a quotation of ``section`` is located, in some recognised form, in a supplied text."""
    from ..adapters.markdown import cited_quotation_spans
    from ..adapters.sources import check_excerpt
    for _a, _b, inner in cited_quotation_spans(section):
        q = inner.strip()
        if len(q) < 3:
            continue
        if any(check_excerpt(q, d, docs).located for d in docs):
            return True
    return False


def _named_document(name_tokens: tuple[str, ...], docs: dict[str, Any]) -> Optional[Any]:
    """The supplied text a claim names: "Source A" by its id or title, a kind ("the extract", "the table") by a title or id
    naming that kind, else the one supplied text."""
    def toks(x: str) -> tuple[str, ...]:
        return tuple(t for _s, _e, t in token_spans(x or ""))
    if name_tokens[:1] == ("source",) and len(name_tokens) == 2:
        for d in docs.values():
            if toks(d.document_id)[:2] == name_tokens or toks(d.title or "")[:2] == name_tokens:
                return d
        return None
    kind = name_tokens[-1]
    named = [d for d in docs.values() if kind in toks(d.title or "") or kind in toks(d.document_id)]
    if len(named) == 1:
        return named[0]
    return next(iter(docs.values())) if len(docs) == 1 else None


def _attributions(text: str) -> list[tuple[tuple[str, ...], int, int]]:
    """``(document name tokens, start, end of the attributed content)`` for every attribution of ``text`` ("Source A shows
    that X", "the extract suggests X"): the content runs from after the verb (and "that") to the clause's end."""
    spans = _tokens(text)
    out: list[tuple[tuple[str, ...], int, int]] = []
    for k, (_s, e, t) in enumerate(spans):
        if t not in ATTRIBUTION_VERBS or k == 0:
            continue
        prev = spans[k - 1][2]
        if k >= 2 and spans[k - 2][2] == "source" and len(prev) == 1 and text[spans[k - 1][0]].isupper():
            name = ("source", prev)
        elif prev in ATTRIBUTION_KINDS and k >= 2 and spans[k - 2][2] in ("the", "this"):
            name = (prev,)
        else:
            continue
        start = e
        if k + 1 < len(spans) and spans[k + 1][2] == "that":
            start = spans[k + 1][1]
        m = re.search(r"[.;:!?](?:\s|$)", text[start:start + 1000])
        end = start + (m.start() if m else min(len(text) - start, 1000))
        out.append((name, start, end))
    return out


def evd_src_002(rctx: Any) -> Iterable[NamedDiagnostic]:
    """EVD-SRC-002 (info): a claim attributes content to a named supplied document, no quotation of its answer section is
    located in a supplied text, and the attributed content has at least three content words, fewer than 60 % of which occur
    in that document: the attribution was not checked (a paraphrase cannot be checked deterministically)."""
    report = rctx.report
    docs = {t.document_id: t for t in report.supplied_texts}
    if not docs:
        return ()
    sections = _paragraph_sections(report)
    exempt: dict[str, bool] = {}
    out: list[NamedDiagnostic] = []
    for c in list(report.claims)[:_MAX_CLAIMS]:
        masked = _masked(c.claim_text)
        for name, a, b in _attributions(masked):
            doc = _named_document(name, docs)
            if doc is None:
                continue
            content = _stems(masked[a:b])
            if len(content) < _ATTRIBUTION_MIN_STEMS:
                continue
            share = Fraction(len(content & _text_stems(doc.text[:_MAX_TEXT])), len(content))
            if share >= _ATTRIBUTION_SHARE:
                continue
            section = sections.get(c.claim_id, report.original_response)
            if section not in exempt:
                exempt[section] = _located_quotation(section, docs)
            if exempt[section]:
                break
            out.append(named_diagnostic(
                "EVD-SRC-002", layer="report", claim_ids=[c.claim_id], derivation="source_text",
                evidence=[_span("claim", c.claim_id, c.claim_text[a:b], a, b), _span("supplied_text", doc.document_id, doc.text[:300])],
                message=(f"the claim attributes to {doc.document_id} content ('{_cut(c.claim_text[a:b], 120)}') of which only {share.numerator * 100 // share.denominator}% "
                         "of the content words occur in that document, and no quotation of its section is located in a supplied text: the "
                         "attribution was not checked (a paraphrase cannot be checked deterministically; this does not say it is false)")))
            break
    return out


#: Stance words (EVD-SRC-006): a closed table of the words that state an attitude to something, approving or
#: disapproving. A paraphrase that credits a document with one stance where the document states only the other says the
#: opposite of the source. Ambiguous words ("just", "content", "positive", "object", "resistance") are left out.
APPROVING_WORDS: frozenset[str] = frozenset("""
accept accepted accepts accepting acceptance welcome welcomed welcomes welcoming approve approved approves approving approval
support supported supports supporting endorse endorsed endorses endorsement embrace embraced embraces agree agreed agrees agreement
praise praised praises celebrate celebrated celebrates willing willingly fair reasonable generous lenient satisfied glad
favourable favorable favoured favored enthusiastic enthusiasm grateful gratitude
""".split())
DISAPPROVING_WORDS: frozenset[str] = frozenset("""
protest protested protests protesting reject rejected rejects rejecting rejection refuse refused refuses refusing refusal
oppose opposed opposes opposing opposition condemn condemned condemns condemnation resent resented resents resentment denounce
denounced denounces criticise criticised criticises criticize criticized criticizes criticism humiliation humiliating humiliated
unwilling reluctant reluctantly objected objects objection resisted unfair unjust harsh punitive outrage outraged anger angry
hostile hostility dismayed bitter bitterness
""".split())
_STANCE_NEGATORS = frozenset({"not", "never", "no", "nor", "hardly", "without", "neither"})
_STANCE_WINDOW = 3


def _stance_side(spans: list[tuple[int, int, str]], k: int, text: str) -> int:
    """1 for an approving and -1 for a disapproving stance word at token ``k``, read the other way when a negator stands within
    :data:`_STANCE_WINDOW` tokens before it in its clause ("did not accept" disapproves; "not unfair" approves); 0 for any other
    token. The clause start is read back at most as far as the window (constant time per token: accuracy round 2,
    V1-STANCE-QUADRATIC)."""
    t = spans[k][2]
    side = 1 if t in APPROVING_WORDS else -1 if t in DISAPPROVING_WORDS else 0
    if not side:
        return 0
    start = _clause_start(spans, k, text, _STANCE_WINDOW)
    if any(w in _STANCE_NEGATORS or w.endswith("n't") for _a, _b, w in spans[max(start, k - _STANCE_WINDOW):k]):
        side = -side
    return side


def _stances(text: str) -> tuple[set[str], set[str]]:
    """``(approving, disapproving)`` stance words of ``text`` (quotations included: a document's quoted words are its
    content), each read the other way when a negator stands within three tokens before it in its clause ("did not accept"
    disapproves; "not unfair" approves). One linear pass (:func:`_stance_side`)."""
    spans = _tokens(text)
    approve: set[str] = set()
    disapprove: set[str] = set()
    for k, (_s, _e, t) in enumerate(spans):
        side = _stance_side(spans, k, text)
        if side:
            (approve if side > 0 else disapprove).add(t)
    return approve, disapprove


#: Where a clause of a document or of a claim ends for the stance readings: a clause mark, a sentence end, or a word that
#: joins clauses.
_CLAUSE_MARKS = ",;:(—–.!?"
_CLAUSE_WORDS = frozenset({"because", "since", "although", "though", "while", "whereas", "and", "but", "so", "as", "however"})
#: Words between a holder and a passive stance word ("the water tax was strongly opposed by farmers"): no words of what the
#: stance is about.
_STANCE_AUXILIARIES = frozenset({"is", "are", "was", "were", "be", "been", "being", "has", "have", "had", "widely", "strongly", "deeply",
                                 "generally", "largely", "bitterly", "warmly", "openly"})


def _clause_ids(spans: list[tuple[int, int, str]], text: str) -> list[int]:
    """The clause number of every token: a new clause starts after a clause mark or a sentence end (:data:`_CLAUSE_MARKS`) and
    at a word that joins clauses (:data:`_CLAUSE_WORDS`). One pass."""
    ids = [0] * len(spans)
    for j in range(1, len(spans)):
        gap = text[spans[j - 1][1]:spans[j][0]]
        ids[j] = ids[j - 1] + (1 if (any(ch in gap for ch in _CLAUSE_MARKS) or spans[j][2] in _CLAUSE_WORDS) else 0)
    return ids


#: Object pronouns right after a stance word by which a clause speaks of what the clause before it named ("The new water tax was
#: introduced in May. Farmers welcomed it warmly."): the two clauses are one statement about it.
_STANCE_OBJECT_PRONOUNS = frozenset({"it", "them", "this", "these", "those"})


def _stance_index(text: str) -> dict[str, tuple[bool, bool]]:
    """``{content stem: (some statement that holds it holds no approving word, some statement that holds it holds no
    disapproving word)}`` of a document (accuracy round 2, V1I-01): what the stance reading of EVD-SRC-006 needs to tell
    whether every statement the document makes about a thing carries one stance. A statement is a clause (:func:`_clause_ids`),
    joined to the clause before it when its stance word governs an object pronoun ("Farmers welcomed it warmly" after "The new
    water tax was introduced in May."). One pass over the tokens; each clause's stems are read once, so the index costs what
    the text does (V1-STANCE-QUADRATIC: the round-1 clause reading copied a clause's stems for every stance word)."""
    spans = _tokens(text)
    ids = _clause_ids(spans, text)
    clauses: list[tuple[tuple[str, ...], set[int], bool]] = []  # (stems, stance sides, its stance word governs an object pronoun)
    k = 0
    n = len(spans)
    while k < n:
        j = k
        sides: set[int] = set()
        back = False
        while j < n and ids[j] == ids[k]:
            side = _stance_side(spans, j, text)
            if side:
                sides.add(side)
                back = back or (j + 1 < n and ids[j + 1] == ids[k] and spans[j + 1][2] in _STANCE_OBJECT_PRONOUNS)
            j += 1
        clauses.append((content_stems([w for _a, _b, w in spans[k:j]]), sides, back))
        k = j
    index: dict[str, tuple[bool, bool]] = {}
    for i, (stems, sides, _back) in enumerate(clauses):
        if i + 1 < len(clauses) and clauses[i + 1][2]:
            sides = sides | clauses[i + 1][1]  # the next clause states its stance on what this one names, by a pronoun
        no_approve, no_disapprove = 1 not in sides, -1 not in sides
        for stem_ in stems:
            was = index.get(stem_, (False, False))
            index[stem_] = (was[0] or no_approve, was[1] or no_disapprove)
    return index


#: Verbs by which a holder judges what stands between them and a stance word after it ("thought the treaty fair", "found the
#: terms harsh"): the stance is about those words, never about the holder before the verb.
_JUDGING_VERBS = frozenset("""
think thinks thought find finds found consider considers considered call calls called judge judges judged deem deems deemed believe
believes believed declare declares declared pronounce pronounces pronounced feel feels felt
""".split())


def _stance_object(text: str) -> set[str]:
    """The stems of what the first stance word of a claim's attributed content is about (accuracy round 2, V1I-01): the words
    after it to the end of its clause ("opposed the water tax, because ...": water, tax), never its holder ("farmers"). For a
    passive ("the water tax was opposed by farmers") the words of its clause before it, the auxiliaries aside; for a stance
    word with no content word after it in its clause, the words between it and the last judging verb before it ("the German
    delegate thought the treaty fair": treaty; :data:`_JUDGING_VERBS`), else the words of its clause before it, the auxiliaries
    aside ("the treaty was fair"). Empty when the text holds no stance word. Linear."""
    spans = _tokens(text)
    ids = _clause_ids(spans, text)
    for k in range(len(spans)):
        if not _stance_side(spans, k, text):
            continue
        after = [w for (_a, _b, w), c in zip(spans[k + 1:], ids[k + 1:]) if c == ids[k]]
        passive = bool(after) and after[0] == "by"
        about = set() if passive else set(content_stems(after))
        if not about:
            before = [w for (_a, _b, w), c in zip(spans[:k], ids[:k]) if c == ids[k]]
            if not passive:
                judged = max((i for i, w in enumerate(before) if w in _JUDGING_VERBS), default=-1)
                before = before[judged + 1:]  # the holder stands before the judging verb
            about = set(content_stems([w for w in before if w not in _STANCE_AUXILIARIES]))
        return about
    return set()


def evd_src_006(rctx: Any) -> Iterable[NamedDiagnostic]:
    """EVD-SRC-006 (source_mismatch, warning): a claim attributes content to a named supplied document ("Source A shows that
    ..."), the attributed content states one stance only (approving or disapproving, :data:`APPROVING_WORDS`,
    :data:`DISAPPROVING_WORDS`, negation read), the document states only the other, and the two share a content word beyond
    the stance words (what the stance is about: "treaty"). The paraphrase credits the source with the opposite of what it
    says (repair round 2, NAME-E04A: "the delegate accepted the treaty as a fair settlement" for "a humiliation ... we sign
    it only under protest"). A document stating both stances, or content stating both, is never read.

    Accuracy round 2 (V1I-01, a reading narrowed in round 1 that still misfired, reverted to the base's behaviour for its
    class): the stance reading is decided only where every clause of the document that speaks of what the claim's stance is
    about (:func:`_stance_object`: the words the stance word governs, never its holder) holds a stance word of the opposite
    side (:func:`_stance_index`). A document that speaks of it anywhere without a stance word of the closed lists ("Farmers
    welcomed the heavy rain in April, but the new water tax angered them deeply": "angered" is no listed word) states a
    stance the lists may not read, so nothing is diagnosed there, as on the committed base. Round 1's clause reading
    (``_stance_clauses``, which counted the holder's word as what the stance is about) is removed. A clause whose stance word
    governs an object pronoun speaks of what the clause before it names ("The new water tax was introduced in May. Farmers
    welcomed it warmly."). Given up: a document that states its stance on the subject in other words than the claim's ("Germany
    signed the treaty in June 1919; its delegates welcomed the settlement as fair") or by a subject pronoun."""
    report = rctx.report
    docs = {t.document_id: t for t in report.supplied_texts}
    if not docs:
        return ()
    out: list[NamedDiagnostic] = []
    read: dict[str, tuple[set[str], set[str], frozenset[str], dict[str, tuple[bool, bool]]]] = {}
    stance_stems = _stems(" ".join(sorted(APPROVING_WORDS | DISAPPROVING_WORDS)))
    for c in list(report.claims)[:_MAX_CLAIMS]:
        masked = _masked(c.claim_text)
        for name, a, b in _attributions(masked):
            doc = _named_document(name, docs)
            if doc is None:
                continue
            approve, disapprove = _stances(c.claim_text[a:b])
            if bool(approve) == bool(disapprove):
                continue
            if doc.document_id not in read:
                d_approve, d_disapprove = _stances(doc.text[:_MAX_TEXT])
                read[doc.document_id] = (d_approve, d_disapprove, _text_stems(doc.text[:_MAX_TEXT]), _stance_index(doc.text[:_MAX_TEXT]))
            d_approve, d_disapprove, d_stems, d_index = read[doc.document_id]
            mine, theirs, stated = (approve, d_disapprove, d_approve) if approve else (disapprove, d_approve, d_disapprove)
            if not theirs or stated:
                continue
            about = (_stems(masked[a:b]) - stance_stems - set(name)) & d_stems
            if not about:
                continue
            target = (_stance_object(c.claim_text[a:b]) - stance_stems - set(name)) & d_stems
            lacking = 1 if approve else 0  # the document's side is the opposite one: the flag of a clause without a word of it
            if not target or any(d_index.get(s, (True, True))[lacking] for s in target):
                # the document speaks of what the claim's stance is about without a stance word of the lists, or not at all:
                # its stance there is not read, so no stance of the source is contradicted (accuracy round 2, V1I-01)
                continue
            what = "an approving" if approve else "a disapproving"
            out.append(named_diagnostic(
                "EVD-SRC-006", layer="report", claim_ids=[c.claim_id], derivation="source_text",
                evidence=[_span("claim", c.claim_id, c.claim_text[a:b], a, b), _span("supplied_text", doc.document_id, doc.text[:300])],
                message=(f"the claim credits {doc.document_id} with {what} stance ('{', '.join(sorted(mine)[:4])}') on what it is about "
                         f"({', '.join(sorted(target)[:4])}), but the document states only the opposite stance ('{', '.join(sorted(theirs)[:4])}'), "
                         "in every clause that speaks of it: the source is cited for the opposite of what it says")))
            break
    return out


def _clause_start(tokens_: list[tuple[int, int, str]], k: int, text: str, limit: Optional[int] = None) -> int:
    """The index of the first token of the clause that holds token ``k``: after the last clause mark (, ; : ( —) or reason
    word before it. With ``limit`` the walk back stops after that many tokens (a caller that reads only the last ``limit``
    tokens before ``k`` gets the same answer from ``max(start, k - limit)``, in constant time per token)."""
    j = k
    stop = 0 if limit is None else max(0, k - limit)
    while j > stop:
        gap = text[tokens_[j - 1][1]:tokens_[j][0]]
        if any(ch in gap for ch in ",;:(—–") or tokens_[j - 1][2] in ("because", "since", "although", "though", "while", "whereas", "and", "but", "so", "as"):
            break
        j -= 1
    return j


def evd_lack_002(rctx: Any) -> Iterable[NamedDiagnostic]:
    """EVD-LACK-002 (info): in a task with supplied texts, a claim states a change in a quantity (a trend verb) with no figure
    other than a year or date (quotations masked), and no content word of what changed (the words before the verb in its
    clause) occurs in a supplied text or in the request."""
    report = rctx.report
    if not report.supplied_texts:
        return ()
    known = set()
    for t in report.supplied_texts:
        known |= _text_stems(t.text[:_MAX_TEXT])
    known |= _stems(rctx.task_text or "")
    out: list[NamedDiagnostic] = []
    for c in list(report.claims)[:_MAX_CLAIMS]:
        masked = _masked(c.claim_text)
        spans = _tokens(masked)
        toks = [t for _s, _e, t in spans]
        if any(_is_number(t) and not _is_year(t) and not ((i > 0 and toks[i - 1] in _MONTHS) or (i + 1 < len(toks) and toks[i + 1] in _MONTHS))
               for i, t in enumerate(toks)):
            continue  # it states a figure
        for k, t in enumerate(toks):
            if t not in TREND_VERBS:
                continue
            j = _clause_start(spans, k, masked)
            subject = masked[spans[j][0]:spans[k][0]] if j < k else ""
            stems = _stems(subject)
            if not stems or stems & known:
                continue
            out.append(named_diagnostic(
                "EVD-LACK-002", layer="report", claim_ids=[c.claim_id], derivation="source_text",
                evidence=[_span("claim", c.claim_id, c.claim_text[spans[j][0]:spans[k][1]], spans[j][0], spans[k][1])],
                message=(f"the claim states that '{_cut(subject, 80)}' {t} with no figure, and what changed occurs in no supplied text and not in "
                         "the request: nothing in scope supports the change (this does not say it is false)")))
            break
    return out


#: Report-layer evidence rules, run in this order after the argument report rules.
REPORT_RULES: tuple[Callable[..., Iterable[NamedDiagnostic]], ...] = (evd_src_006, evd_src_002, evd_lack_002)
