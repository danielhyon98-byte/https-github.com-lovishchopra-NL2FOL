"""The translator channel: every inter-agent message passes through here.

Router -> specialist: ``request`` makes the ask explicit (items, constraints, texts),
wraps it in a signed-hash envelope, checks it against the router's plan and logs it.

Specialist -> router: ``respond`` wraps the report in an envelope that must reply to
the request, then checks identity (same request/task, selected agent, the envelope's
sender is the agent the payload claims to come from, in scope), message integrity
(replay, tampering, a report id reused with another payload), request fidelity (every
required item addressed; every constraint checked, formally where it is arithmetic; a
response that merely restates the request), source integrity (quotations against the
supplied texts, a form difference told apart from an invented quotation), and runs
claim verification through the injected translator. Nothing is delivered silently: the
recipient gets a ``TransmissionReceipt`` and a REJECTED transmission is not delivered at
all. Raw text whose stated sender is not the agent the request was addressed to is
REJECTED before it is parsed, so identity never depends on the adapter; text the branch
adapter cannot turn into a report, and a report whose payload does not re-validate
against the contract, are REJECTED with INT-REQ-009; the channel never raises into the
router.

Agent -> agent: ``relay`` carries a report or a synthesis between agents with the
same envelope, identity and ledger checks (the sender must be the payload's owner and,
like the recipient, a party the plan selected), and cross-checks its formalized claims
against every claim already transmitted in the same request so contradictions between
agents are named, not reconciled. A synthesis is checked for undisclosed contradictions
between the claims it accounts for (INT-CONFLICT-002), for figures and dates (in digits or
words, with their scale words) that occur in none of its sources or are re-paired between
events, for quotations no supplied text or cited report holds (INT-LEDGER-025), for a
reversed direction or a dropped negation (INT-LEDGER-026), for a comparison turned the other
way or a negation added against a single source (INT-LEDGER-030), for an act given to a person its
cited sources do not name for it (INT-LEDGER-032), and, when a synthesized claim
carries (or can be given) a formal conclusion, for entailment by its formalized sources;
when that cannot be checked, the receipt says so instead of implying a check that nobody
ran (INT-LEDGER-011, INT-SYNTH-012). Raw text that is not valid Unicode (a lone UTF-16
surrogate) is refused before parsing (INT-REQ-009); nothing raises into the router. So is a
specialist's response whose own text holds a bidirectional embedding, override or isolate
(rule bidi-text, :data:`BIDI_CONTROL_CLASS`): a reader may be shown that text in another order
than every check reads it, as the combinator port's text rule already refuses in a synthesis.

Branch formal checks (``_branch_checks``) run under the check's named engine policy
(``engine.policies``: ``linear`` is the caller's configuration unchanged; ``nonlinear`` opens
the nonlinear-term gate under a deterministic ``rlimit``); an unknown policy is never run under
another one (INT-SUBJ-002). A check is satisfied only when the engine returns the expected
status with a non-vacuous proof (no E108); it failed when the status is definitive and another
one (INCONSISTENT_PREMISES only when the check counts it as a failure); otherwise it is
undecided. A failure is INT-SUBJ-001 (error) or, for a check that relied on a reading the
report did not state, INT-SUBJ-004 (warning); undecided is INT-SUBJ-002. Each result and finding
names the delivered claims that hold the checked statement (the pack's own claim ids first) and
quotes its clause; every detail and message is cut to its contract length, and an exception while
deciding one check makes that check alone undecided. A branch may lend the channel hub hooks
(``branches.base.BranchHooks``, the STEM branches only): extra request imperatives, extra
coverage words, an echo exemption for an answer that computes, and the word-count view.

Observers (optional; ``docs/OVERSEER_DESIGN.md`` section 5.3). ``TranslatorChannel(observers=...)`` and
``add_observer`` attach callables that receive one immutable ``ChannelEvent`` per call of the four entry points
(``request``, ``respond_text``, ``respond``, ``relay``), built inside the call before anything is returned (see
``channel/events.py``). A private decorator wraps the four entry points and changes nothing else:

* with NO observer it calls the method straight through (one attribute check): the channel behaves exactly as it did
  without the hook, and opens no result capture;
* with observers, the outermost call runs through ``events.observe_call``: the method body, unchanged, runs inside a
  result capture; the event is built from the channel's public state; each observer is called inside ``try/except``,
  and a failure is recorded in the bounded ``observer_errors`` (sequence number, observer name, exception type) and
  never reaches the caller; a method that raised emits a ``raised`` event and its exception is re-raised unchanged;
* a call made while an observed call is in progress (``respond_text`` calling ``respond``; a call an observer makes
  during notification) runs straight through and emits no event of its own, so one router call is one event.

An observer cannot change delivery or the returned objects: the event is immutable and the returned tuple is the
method's own. ``channel_uid`` names the channel instance (uuid4 hex, set at construction): several channels may share
a task id. The channel never imports the overseer package.

Deviations from ``docs/OVERSEER_DESIGN.md`` section 5.3 (stage ``hook``): the decorator delegates the observed call to
``events.observe_call``, the very function the audit stage's manual observation helper drives, so the hook and the
helper cannot drift apart (the per-instance ``ObservationState`` holds ``channel_uid``, the event counter, the depth and
the failures); ``add_observer`` and the read-only ``observers`` are added so a hub can attach an observer that needs the
channel object; ``observer_errors`` is a property returning a copy of the bounded record; a call made while an observed
call is in progress, including one an observer makes during notification, is not observed (it is reported by the audit,
CUST-003); only ``Exception`` raised by an observer is caught (an interrupt still stops the process).

Argument diagnosis (rules ``argdiag-2``, ``named``): the branch formal checks and the constraint-bound
checks are code-built checks, not specialist arguments, so they run with ``diagnose=False``. Every
receipt carries ``named_diagnostics``: each outcome's diagnostics, the report-level diagnostics
(``translate.diag_core.report_diagnostics``, run once per delivered or relayed report) and a named
diagnostic for each structural or integrity finding that carries a ``defect`` (the channel labels existing
codes through ``named.DEFECT_OF_CODE`` when it builds the receipt). Each warning or error diagnostic of an
outcome or of the report level on a material claim is also one INT-ARG-001 finding carrying its ``defect``
(ARG-CONTRA-001 excepted: INT-REQ-007 already states it); info diagnostics never reach ``findings``, so
they never change the receipt status. Two encodings of one claim that reach opposite definitive answers
(a branch formal check of a clause fails while the claim's translation is displayed with a positive
verdict) are INT-XENC-001 (warning); neither verdict is withdrawn. The summary counts the diagnostics
("Argument diagnosis: N named on K claims ...") before the scope tail.
"""
from __future__ import annotations

import functools
import inspect
import itertools
import re
import time
import uuid
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional, Sequence, Union, get_args

from pydantic import BaseModel, ValidationError

from ..engine.errors import DiagnosticCode
from ..engine.policies import UnknownPolicyError, policy_config, policy_limits
from ..engine.results import SolverConfig, VerificationResult
from ..engine.runner import verify
from ..engine.statuses import VerificationStatus as S, is_definitive
from ..integrity.contracts import (AgentMessage, AgentRole, ConflictRecord, IntegrityFinding, LedgerEntry, SYNTHESIS_CITATION_RULE, SYNTHESIZED_CLAIM_TRANSFORMATIONS, Synthesis,
                                   SynthesizedClaim, WorkPlan, payload_hash)
from ..integrity.cross_check import check_conflict_disclosure, check_conflict_records, check_cross_report_consistency, check_paraphrase_coverage, check_synthesis_entailment
from ..integrity.envelope import MessageLog, bind_payload
from ..integrity.handoff import check_report_against_plan
from ..integrity.ledger import check_synthesis_ledger, light_stem
from ..ir.canonical import canonical_json, sha256_hex
from ..ir.schema import Assertion, Problem
from ..named import (
    DEFECT_LABELS,
    MAX_PER_RECEIPT,
    NAMED_CODES,
    NamedDiagnostic,
    defect_of,
    defect_of_check_kind,
    finding_message,
    from_finding,
    ordered as order_named,
    rules_state,
    summary_counts,
)
from ..translate.common import truncate
from ..translate.contracts import ClaimRecord, ClaimVerificationOutcome, SpecialistReport, StructuralFinding, SuppliedText, TaskRecord, TranslationStatus, sha256_text
from ..translate.diag_core import report_diagnostics
from ..translate.grounding import check_claim_sources, locate_excerpt, locate_long_elision, locate_quotation, locate_quotation_inexact
from ..version import ARG_RULES_VERSION
from .citations import citation_evidence
from .contracts import Constraint, ConstraintResult, CoverageRecord, SUMMARY_MAX_CHARS, TaskRequest, TransmissionReceipt, TransmissionStatus
from .cues import VERDICT_CUES, verdict_cue_regex
from .events import ChannelEvent, ObservationState, observe_call
from .request_parser import (LEVEL3_VERDICT_TERMS, about_band, blank_quotations, bound_word_measure, count_answer_words, count_paragraphs, extract_constraints,
                             extract_items, measure_answer_words, measured_of, part_label, per_part_bound, question_label, word_bound_severity)


@dataclass(frozen=True)
class ReportDiagnosis:
    """The report-level argument diagnosis of one delivered report: what it named and the rules that did not finish."""
    diagnostics: tuple[NamedDiagnostic, ...] = ()
    incomplete: tuple[str, ...] = ()


#: Displays that are a positive verdict on the encoding (INT-XENC-001 compares a failed branch check with one of them).
_PASSING = frozenset({S.ENTAILED, S.CONSISTENT, S.SATISFIABLE})

#: The injected claim verifier: ``fn(claim, report)``. A verifier that also declares a ``task`` parameter (or ``**kwargs``)
#: is called ``fn(claim, report, task=<TaskRecord>)`` with the task record of the request the report answers (the router's
#: request text, an application-created record: ``translate.contracts.TaskRecord``), so a premise that claims the task's
#: authority can be validated against the task's own wording and a fidelity reviewer is shown the original task.
VerifyClaimFn = Callable[..., Optional[ClaimVerificationOutcome]]
#: A channel observer: called once per entry-point call with the call's immutable event; its return value is ignored.
ChannelObserver = Callable[[ChannelEvent], None]


def _accepts_task(fn) -> bool:
    """Whether the injected verifier declares a ``task`` parameter (or ``**kwargs``): only then is the task record passed."""
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.name == "task" and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY) or p.kind is p.VAR_KEYWORD for p in params)
#: Given a synthesized claim and the formalized problems of its cited sources, propose the
#: formal conclusion to test (an Assertion over the sources' shared glossary), or None.
FormalizeSynthesisFn = Callable[[SynthesizedClaim, list[Problem]], Optional[Assertion]]
ParseFn = Callable[..., SpecialistReport]

# Cues that state a position on degree (a claim such as "X was responsible for Y" is not one). Built from the shared list
# in ``cues.py`` (:data:`VERDICT_CUES`), which the History parser imports, so the hub and the parser agree on what a verdict is.
_VERDICT_CUE = re.compile(r"\b(" + verdict_cue_regex() + r")\b", re.IGNORECASE)
#: What a branch adapter writes into ``unresolved_issues`` when it folded the claims beyond the contract limit into one
#: tail claim; the channel turns it into a finding naming how much went unchecked (INT-REQ-013). The count is read from the
#: first digit of its run and taken whole (integration gate 3, class sweep of the handoff fixer): searched from every digit
#: of a long run of digits, it read the rest of the run again each time, quadratic in an unresolved issue, which a
#: structured report may carry at any length (2.4 s to receive and 2.5 s to audit one of 16,000 digits); a count can only
#: start where no digit precedes it, so every match is the one the search found before.
_FOLDED_TAIL_RE = re.compile(r"(?<!\d)(?P<n>\d++) (?:claims|sentences) beyond the report's claim limit \((?P<limit>\d++)\) were merged into claim (?P<tail>\S+)")
#: The pattern as it was written before integration gate 3: the reference its linear form is held to (a test reads both).
_FOLDED_TAIL_REFERENCE_RE = re.compile(r"(?P<n>\d+) (?:claims|sentences) beyond the report's claim limit \((?P<limit>\d+)\) were merged into claim (?P<tail>\S+)")
#: A claim roled 'other' is a note (a from-memory label, a self-report, a task note), never an answer to a request item.
_NOTE_ROLE = "other"
#: Roles whose claims may carry the paragraph's verdict when they state a position (a claim roled 'other' never counts).
_VERDICT_ROLES = frozenset({"point", "thesis", "link", "analysis"})
_STOP = frozenset("the a an and or of to in on for with by is are was were be this that these those as at from it its how why what does do into their there which who whom not".split())
#: Error codes that stop delivery: identity, envelope, request binding, unparseable payload, ledger provenance.
_BLOCKING_PREFIXES = ("INT-HANDOFF", "INT-ENV", "INT-REQ-000", "INT-REQ-001", "INT-REQ-002", "INT-REQ-009", "INT-LEDGER-000", "INT-LEDGER-008")
#: Parties to every channel that the plan does not select: the router that opened the task and the roles that read its
#: output. Specialists and combinators must be selected by the plan to send or receive on it.
_INFRASTRUCTURE_ROLES = frozenset({AgentRole.ROUTER, AgentRole.OVERSEER, AgentRole.VERIFIER, AgentRole.RETRIEVAL, AgentRole.GATE})
_NOT_PERFORMED = "NOT performed on this channel: the combinator supplied no formal conclusion for this claim and no formalization hook is configured, so the router must not treat the content change as checked"
#: The grounding module's wording for a quotation whose words occur but whose form differs (initial capital, line-break
#: mark, long elision); the channel reports it as a warning, never as an invented quotation.
_FORM_DIFFERS = "differs in form"
_ECHO_OVERLAP = 0.9
#: Overlap at which a response counts as a restatement when it also quotes the request's own words as the text's.
_ECHO_OVERLAP_QUOTED = 0.75
#: Longest restatement, as a multiple of the request's length: a plain echo (90% overlap) up to 1.5x, a quoted echo (75%
#: overlap and the request's own words quoted as the text's) up to 2x. The quoted rule does not depend on the plain cap.
_ECHO_LENGTH_RATIO = 1.5
_ECHO_QUOTED_LENGTH_RATIO = 2.0
#: Function words (light-stemmed) that a restatement may add without adding content ("in", "is", "so", "through"): the
#: echo overlap is measured on the other stems, so "... through personification and the turn" is still a restatement.
_ECHO_FUNCTION = frozenset(light_stem(w) for w in (" ".join(sorted(_STOP)) + " so through such both also then than while very own its this these those whose about "
                                                     "them they he she him his her hers we us our you your i me my one ones been being has have had can could would should will "
                                                     "shall may might must just only").split())
_SCOPE_TAIL = "Formal results concern only the encoded checks under their premises; coverage is heuristic."
#: A from-memory label in a claim's sentence: a quotation it carries is unverifiable, never refuted.
_MEMORY_LABEL_RE = re.compile(r"\bfrom memory\b|\bas I recall\b|\bI recall\b|\bif I remember\b", re.IGNORECASE)
#: A word of a supplied text, for the near forms of an altered short quotation.
_NEAR_WORD_RE = re.compile(r"[^\W\d_]+")


@functools.lru_cache(maxsize=64)
def _text_word_index(text: str) -> tuple[tuple[str, ...], dict[str, tuple[int, ...]], dict[str, frozenset[int]]]:
    """``(words, positions, prefix lengths)`` of a supplied text, read once per text: its case-folded words in order, the
    first 64 positions of each word, and for each four-letter prefix the lengths of the words that open with it. The near
    forms of every short quotation of an answer are looked up here, where the text was read again for each one (round-8
    clearance c1, handoff fixer: an answer of many short quotations made the check quadratic)."""
    words = tuple(w.casefold() for w in _NEAR_WORD_RE.findall(text))
    positions: dict[str, list[int]] = {}
    prefixes: dict[str, set[int]] = {}
    for i, w in enumerate(words):
        at = positions.setdefault(w, [])
        if len(at) < 64:
            at.append(i)
        if len(w) >= 4:
            prefixes.setdefault(w[:4], set()).add(len(w))
    return words, {w: tuple(at) for w, at in positions.items()}, {k: frozenset(v) for k, v in prefixes.items()}


def _edit_distance(a: str, b: str, cap: int) -> int:
    """Levenshtein distance of two words, stopped once it exceeds ``cap`` (``cap + 1`` then)."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def _near_word(word: str, other: str) -> bool:
    """``other`` is a near form of ``word``: both of four letters or more sharing their first three ("amigos",
    "amistades"), or within an edit distance of a third of the longer word ("amistad", "amistades")."""
    if word == other or not word or not other:
        return False
    if min(len(word), len(other)) >= 4 and word[:3] == other[:3]:
        return True
    cap = max(1, max(len(word), len(other)) // 3)
    return _edit_distance(word[:40], other[:40], cap) <= cap


def displaced_word(excerpt: str, text: str) -> bool:
    """Rule ``short-near-miss`` (round-8 clearance c1, sp-t13): a two-word quotation one of whose words the text holds next
    to a near form of its other word (:func:`_near_word`), in the quotation's order: «crecen amigos» where the text says
    «crecen amistades». The text holds the quotation altered, so it is refutable, not merely unverifiable. One lookup per
    occurrence of the word held (at most 64)."""
    ex = [w.casefold() for w in _NEAR_WORD_RE.findall(excerpt[:400])]
    if len(ex) != 2:
        return False
    words, positions, _prefixes = _text_word_index(text)
    held = [w in positions for w in ex]
    if held.count(True) != 1:
        return False
    k = held.index(True)
    anchor, missing = ex[k], ex[1 - k]
    for i in positions[anchor]:
        j = i + 1 if k == 0 else i - 1
        if 0 <= j < len(words) and _near_word(missing, words[j]):
            return True
    return False
_SUMMARY_TRUNCATED = " ...[summary truncated] "
_MAX_NAMED = 8
#: Contract lengths of a ConstraintResult detail and of a finding message.
_DETAIL_MAX = 2000
_VACUOUS = DiagnosticCode.VACUOUS_RESULT.value
#: Wall-clock budget for the STEM checks of one report (kinds ``stem_*``): checks left when it is spent are undecided
#: (INT-SUBJ-002, "check budget"), never success. Other packs' checks are not budgeted. It is also the upper bound of a
#: channel's own ``stem_budget_s`` (the integration checks port sets it from what is left of a call's budget).
STEM_CHECK_BUDGET_S = 8.0


def stem_budget_s(requested: Optional[float]) -> float:
    """The STEM check budget a channel uses: :data:`STEM_CHECK_BUDGET_S`, or a smaller per-channel budget (never a larger
    one, never below zero). ``None`` is the module budget itself, so a channel nobody configured behaves exactly as before."""
    if requested is None:
        return STEM_CHECK_BUDGET_S
    try:
        value = float(requested)
    except (TypeError, ValueError):
        return STEM_CHECK_BUDGET_S
    if value != value:  # NaN never widens the budget
        return 0.0
    return min(STEM_CHECK_BUDGET_S, max(0.0, value))
#: A UTF-16 surrogate code point. In a Python string every one is unpaired as far as Unicode is concerned (a truncated
#: emoji arriving in an agent's JSON as "\\ud83d"): it has no UTF-8 form and no contract accepts it, so text carrying one
#: is rejected at the channel boundary (INT-REQ-009) before it is parsed or hashed.
_SURROGATE_RE = re.compile("[\ud800-\udfff]")
#: The bidirectional embeddings, overrides and isolates and the marks that close them (U+202A to U+202E, U+2066 to U+2069):
#: the bidirectional class of the combinator port's text rule (``integrity.contracts.SYNTHESIS_FORBIDDEN_CLASS``). The text
#: one governs may be shown to a reader in another order than the order every check of the hub reads ('5.0' after U+202E is
#: displayed '0.5'; a date, a quotation or a sum in an isolate is reordered alike), so a specialist's response whose own text
#: holds one is refused (INT-REQ-009, rule bidi-text) as a synthesis holding one already is: no receipt of any subject shows a
#: check result for text a reader sees in another order. Round-8 clearance c1 (STEM-integration finding 17): the STEM pack
#: declines to decide a relation such a control reaches (rule bidi-control), but a humanities answer's claims, which it never
#: reads, were translated and checked in the order the hub reads them. The marks U+200E, U+200F and U+061C reorder no run of
#: text and are not refused.
BIDI_CONTROL_CLASS = "\u202a-\u202e\u2066-\u2069"
_BIDI_CONTROL_RE = re.compile(f"[{BIDI_CONTROL_CLASS}]")
_BIDI_CONTROLS = ("\u202a", "\u202b", "\u202c", "\u202d", "\u202e", "\u2066", "\u2067", "\u2068", "\u2069")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


#: A word for the coverage heuristic: letters with internal apostrophes or hyphens only, so a quotation mark or a closing
#: single mark ("'smokeless air'") never sticks to a term.
_TERM_RE = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")


def _place_of(word: str) -> str:
    """A capitalised adjective of place read as its place ("African" -> "africa", "European" -> "europe", "Russian" ->
    "russia"), so an item about "Africa" and a claim about "African states" share a term. Applied to both sides of the
    comparison alike; any other word is returned unchanged (case-folded)."""
    low = word.casefold()
    if len(word) >= 6 and word[0].isupper() and low.endswith("an"):
        return low[:-2] if low.endswith("ean") else low[:-1]
    return low


def _terms(text: str) -> set[str]:
    """Content terms of ``text`` for the coverage heuristic: quotation marks and a possessive ``'s`` stripped, function
    words dropped, an adjective of place read as its place (:func:`_place_of`), then light-stemmed (``light_stem``, the
    echo test's rule), so "the poem's 'smokeless air'" shares ``poem``, ``smokeless`` and ``air`` with a claim about the
    smokeless air of the poem, and "decolonisation in Africa" shares ``africa`` with "African states"."""
    out: set[str] = set()
    for w in _TERM_RE.findall(text):
        if w.endswith(("'s", "’s")):
            w = w[:-2]
        w = _place_of(w)
        if len(w) < 3 or w in _STOP:
            continue
        out.add(light_stem(w))
    return out


#: The label a request gives an item before its text ("Guiding question:", "Essay question:", "Question 2:"): not a term
#: the answer must repeat.
#: Every blank run is possessive (integration gate 3): the runs before and after the optional qualifier met only through it
#: (quadratic in a long item); no item after a run starts with a blank, so every match is the one the backtracking form found.
_ITEM_LABEL_RE = re.compile(r"^\s*+(?:guiding|essay|research|prescribed|key|focus)?\s*+(?:question|title|prompt|task)(?:\s++\d+)?\s*+:\s*+", re.IGNORECASE)
#: Markup an answer may wrap its part labels in ("**Part (a) — find**", "$x$").
_MARKUP_CHARS_RE = re.compile(r"[*_`$#]")


def _answer_sections(text: str) -> list[tuple[int, frozenset[str]]]:
    """``(offset, labels)`` for every line of the answer (markup removed) that opens with a part label: "(a)", "Part
    (b) —", "1.", and a nested "3. a)" (labels 3 and a), or with a question heading ("Question 2 [5 marks]": label q2,
    ``request_parser.question_label``; round-8 clearance c1). Offsets are in the markup-free text."""
    from .request_parser import part_label, question_label
    plain = _MARKUP_CHARS_RE.sub("", text)
    out: list[tuple[int, frozenset[str]]] = []
    pos = 0
    for line in plain.split("\n"):
        lab = part_label(line) or question_label(line)
        if lab is not None:
            labels = {lab}
            rest = re.sub(r"^\W{0,4}(?:part\s+)?\(?[0-9a-z]{1,4}[.)]\)?\s*", "", line.strip(), flags=re.IGNORECASE)
            inner = part_label(rest) if rest else None
            if inner is not None and inner != lab:
                labels.add(inner)
            out.append((pos, frozenset(labels)))
        pos += len(line) + 1
    return out


def _claim_sections(text: str, sections: list[tuple[int, frozenset[str]]], claims: list[ClaimRecord]) -> dict[str, frozenset[str]]:
    """Per claim, the labels of the answer section its text stands in (located by its first words, markup ignored)."""
    plain = _MARKUP_CHARS_RE.sub("", text)
    out: dict[str, frozenset[str]] = {}
    for c in claims:
        words = re.findall(r"\S+", _MARKUP_CHARS_RE.sub("", c.claim_text))[:8]
        if not words:
            continue
        m = re.search(r"\s+".join(re.escape(w) for w in words), plain)
        if m is None:
            continue
        before = [labels for start, labels in sections if start <= m.start()]
        if before:
            out[c.claim_id] = before[-1]
    return out


def _paragraph_key(claim_id: str) -> str:
    """The paragraph a claim id names ("g7.1" -> "g7", "p1-s03" -> "p1", "h1.4" -> "h1"); the id itself otherwise."""
    m = re.match(r"^([A-Za-z]*\d+)[.\-]", claim_id)
    return m.group(1) if m else claim_id


def _tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def _is_blocking(findings) -> bool:
    """A transmission is withheld only for identity, envelope, request-binding, parse and
    ledger-provenance errors; a report delivered with findings counts as transmitted."""
    return any(f.severity == "error" and f.code.startswith(_BLOCKING_PREFIXES) for f in findings)


#: The contracts' own model-validator messages that hold no agent text (fixed sentences): the only validator messages a
#: receipt repeats, so a synthesis refused for a wrong text digest says so instead of 'value_error' (integration gate,
#: round 1, combinator-faults-11).
_FIXED_VALIDATOR_MESSAGES = frozenset({
    "text_sha256 does not match text", "duplicate synthesized claim_id", "payload_sha256 does not match payload", "plan_sha256 does not match the plan",
    "conflict record lists the same claim id more than once; a conflict needs two distinct parties", SYNTHESIS_CITATION_RULE})
#: What a synthesis text that breaks the contract's text rule (``integrity.contracts.SYNTHESIS_TEXT_PATTERN``) is refused for:
#: the rule, never the text (integration gate 1, harness handoff 1).
_SYNTHESIS_TEXT_RULE = ("the synthesis text rule: at least one visible character, no control character other than a tab or a line break, "
                        "no bidirectional embedding, override or isolate")


def _shape_reason(exc: BaseException, contract: str = "report") -> str:
    """Describe why parsing or validation failed without echoing the agent's text. A model-level error (no field location)
    is named by ``contract``, with the validator's own message when it is one of :data:`_FIXED_VALIDATOR_MESSAGES` (a nested
    model's fixed message is stated at its location too); a synthesis text that breaks the text rule states the rule."""
    if isinstance(exc, ValidationError):
        parts = []
        for e in exc.errors()[:6]:
            loc = ".".join(str(x) for x in e.get("loc", ()))
            part = f"{loc or contract}: {e.get('type', 'invalid')}"
            if e.get("type") == "value_error":
                msg = str(e.get("msg", ""))
                msg = msg[len("Value error, "):] if msg.startswith("Value error, ") else msg
                if msg in _FIXED_VALIDATOR_MESSAGES:
                    part = f"{loc or contract}: {msg}"
            elif e.get("type") in ("string_pattern_mismatch", "string_too_short") and contract == "synthesis":
                part = f"{part} ({_SYNTHESIS_TEXT_RULE})"
            parts.append(part)
        more = len(exc.errors()) - 6
        return "; ".join(parts) + (f"; +{more} more" if more > 0 else "")
    return str(exc)[:300]


def _full_dump(model: BaseModel) -> Optional[dict]:
    """``model``'s JSON dump with every field, None kept: the form in which a None in a field that has a default but is not
    Optional fails validation (the exclude-None dump a payload is delivered as leaves it out, and the recipient would read
    the default). None when the object cannot be dumped (built around its contract's validation); never raises."""
    try:
        return model.model_dump(mode="json")
    except Exception:  # noqa: BLE001 - an object that cannot be dumped is refused by the caller, never raised
        return None


def _text_attr(model: Any, name: str) -> Optional[str]:
    """``model``'s attribute ``name`` when it is a string, scrubbed of surrogates and cut to an identifier's 128 characters;
    None when it is missing or of another type (an object built around its contract's validation). For the identifiers a
    refusal names before the payload is re-validated (integration gate 3); never raises."""
    try:
        value = getattr(model, name, None)
    except Exception:  # noqa: BLE001 - a property that raises names nothing
        return None
    return _scrub(value)[:128] if isinstance(value, str) else None


def _fit_summary(summary: str, limit: int = SUMMARY_MAX_CHARS) -> str:
    """Keep a receipt summary within the contract limit, cutting the body and never the scope sentence."""
    if len(summary) <= limit:
        return summary
    tail = _SCOPE_TAIL if summary.endswith(_SCOPE_TAIL) else ""
    body = summary[: len(summary) - len(tail)]
    room = limit - len(tail) - len(_SUMMARY_TRUNCATED)
    return body[:room].rstrip() + _SUMMARY_TRUNCATED + tail


def surrogate_offsets(text: str) -> list[int]:
    """Character offsets of the UTF-16 surrogate code points in ``text`` (empty for valid Unicode text)."""
    return [m.start() for m in _SURROGATE_RE.finditer(text)] if text else []


def _scrub(text: str) -> str:
    """``text`` with every surrogate code point replaced by U+FFFD, for identifiers echoed into findings and envelopes."""
    return _SURROGATE_RE.sub("\ufffd", text) if text else text


def _surrogate_message(what: str, offsets: list[int]) -> str:
    shown = ", ".join(str(o) for o in offsets[:_MAX_NAMED]) + (f" and {len(offsets) - _MAX_NAMED} more" if len(offsets) > _MAX_NAMED else "")
    return (f"{what} carries {len(offsets)} lone UTF-16 surrogate code point(s) at character offset(s) {shown} (a truncated or split "
            f"character such as half an emoji): it is not valid Unicode text, so it was neither parsed nor delivered")


def _bidi_count(text: str) -> int:
    """How many bidirectional embeddings, overrides, isolates and closing marks ``text`` holds: one C-level count per code point,
    so a text made of nothing else (400,000 of them) is counted in milliseconds, never matched one by one in Python."""
    return sum(text.count(ch) for ch in _BIDI_CONTROLS)


def bidi_control_message(what: str, text: str) -> Optional[str]:
    """Rule bidi-text: why ``text`` (the ``what`` of a specialist's response) is refused, naming the first bidirectional
    embeddings, overrides and isolates it holds (:data:`BIDI_CONTROL_CLASS`) by code point and character offset and
    counting the rest, never quoting the text; None when it holds none. One pass over the text."""
    if not isinstance(text, str) or not text or _BIDI_CONTROL_RE.search(text) is None:
        return None
    n = _bidi_count(text)
    first = [f"U+{ord(m.group()):04X} at character offset {m.start()}" for m in itertools.islice(_BIDI_CONTROL_RE.finditer(text), _MAX_NAMED)]
    shown = ", ".join(first) + (f" and {n - len(first)} more" if n > len(first) else "")
    return (f"{what} carries {n} bidirectional embedding, override or isolate character(s) ({shown}): a reader may be shown the text "
            "it governs in another order than the order every check of the hub reads, so it was neither checked nor delivered (rule "
            "bidi-text: the text rule the combinator port holds a synthesis to)")


def _report_texts(report: SpecialistReport):
    """``(where, claim id or None, text)`` for every text of a report that is the specialist's own: the response, the report's
    assumptions and unresolved issues, and each claim's text, assumptions, assessment criteria and source references (excerpt and
    locator). The supplied texts are the router's and are not read."""
    yield "the response text", None, report.original_response
    for a in report.assumptions:
        yield "an assumption of the report", None, a
    for a in report.unresolved_issues:
        yield "an unresolved issue of the report", None, a
    for c in report.claims:
        yield "the text of claim", c.claim_id, c.claim_text
        for a in [*c.assumptions, *c.assessment_criteria]:
            yield "an assumption of claim", c.claim_id, a
        for r in c.source_refs:
            for t in (r.excerpt, r.locator):
                if t:
                    yield "a source reference of claim", c.claim_id, t


def report_bidi_findings(report: SpecialistReport) -> list[IntegrityFinding]:
    """Rule bidi-text on a report (a response received as a structured payload, or handed to ``respond``): INT-REQ-009
    (error, blocking) when the specialist's own text (:func:`_report_texts`) holds a bidirectional embedding, override or
    isolate, naming the first place and the claims holding one; [] otherwise. Never raises: a report built around its
    contract's validation is the re-validation's to refuse."""
    try:
        named: list[str] = []
        claims: list[str] = []
        n = 0
        for where, cid, text in _report_texts(report):
            if not isinstance(text, str) or _BIDI_CONTROL_RE.search(text) is None:
                continue
            n += _bidi_count(text)
            if len(named) < _MAX_NAMED:
                label = where if cid is None else f"{where} {_BIDI_CONTROL_RE.sub(chr(0xFFFD), _scrub(str(cid)))[:128]}"
                named += [f"U+{ord(m.group()):04X} at character offset {m.start()} of {label}"
                          for m in itertools.islice(_BIDI_CONTROL_RE.finditer(text), _MAX_NAMED - len(named))]
            if cid is not None and cid not in claims:
                claims.append(cid)
        if not n:
            return []
        shown = "; ".join(named) + (f" and {n - len(named)} more" if n > len(named) else "")
        rid, aid = _text_attr(report, "report_id"), _text_attr(report, "agent_id")
        return [IntegrityFinding(code="INT-REQ-009", severity="error",
                                 message=(f"report payload carries {n} bidirectional embedding, override or isolate character(s) in the specialist's own text "
                                          f"({shown}): a reader may be shown the text it governs in another order than the order every check of the hub "
                                          "reads, so it was neither checked nor delivered (rule bidi-text: the text rule the combinator port holds a synthesis to)"),
                                 claim_ids=[c for c in claims if isinstance(c, str)][:64], report_ids=[rid] if rid else [], agent_ids=[aid] if aid else [])]
    except Exception:
        return []


def _named(ids: list[str]) -> str:
    shown = ", ".join(ids[:_MAX_NAMED])
    return shown + (f" and {len(ids) - _MAX_NAMED} more" if len(ids) > _MAX_NAMED else "")


def _material_claims(report: SpecialistReport) -> list[ClaimRecord]:
    """The claims that answer: everything not roled 'other' (notes and self-reports never count)."""
    return [c for c in report.claims if c.claim_role != _NOTE_ROLE]


def _content_dump(report: SpecialistReport) -> dict:
    """The report without its delivery timestamp: what a re-delivery is compared on (INT-ENV-001 vs INT-HANDOFF-015)."""
    return report.model_dump(mode="json", exclude_none=True, exclude={"created_at"})


def _norm_text(text: str) -> str:
    return " ".join(text.split()).casefold()


#: A sentence that defers the deliverable to the student's reply (round-8 clearance c1, ps-p8d: 'Reply "approve" and I will
#: write the full evaluation within 500 words.'): the answer is a plan or a question back, not the deliverable. The deferred
#: object must name the deliverable ("the full evaluation", "the essay", "your answer"), so an offer of something more after
#: a complete answer ("let me know and I can add an example") defers nothing. Every run is bounded.
_DEFERRED_OBJECT = (r"(?:the|a|your|my)\s+(?:(?:full|complete|whole|entire|final)\b[^.!?\n]{0,40}?"
                    r"|(?:essay|answer|response|evaluation|report|analysis|draft|section|sections|paragraph|commentary|discussion)\b)")
_DEFERRAL_RE = re.compile(
    r"(?:^|(?<=[.!?:\n])\s{0,3})(?:(?:reply|respond|answer|write\s+back|say|tell\s+me|let\s+me\s+know|confirm)\b[^.!?\n]{0,120}?\b(?:and|then|so)\s+I"
    r"(?:'ll|’ll|\s+will|\s+can|\s+shall)\s+(?:write|draft|produce|give|send|complete|finish)\s+(?:you\s+)?" + _DEFERRED_OBJECT
    + r"|(?:once|when|if|after)\s+you\s+(?:approve|confirm|agree|reply|say\s+so|let\s+me\s+know|are\s+happy)\b[^.!?\n]{0,120}?\bI(?:'ll|’ll|\s+will|\s+can|\s+shall)\s+"
    r"(?:write|draft|produce|give|send|complete|finish)\s+(?:you\s+)?" + _DEFERRED_OBJECT
    + r"|(?:shall|should)\s+I\s+(?:write|draft|produce|go\s+ahead\s+(?:and|with))\b[^.!?\n]{0,40}?" + _DEFERRED_OBJECT + r"[^.!?\n]{0,80}?\?"
    + r"|(?:do\s+you\s+want|would\s+you\s+like)\s+me\s+to\s+(?:write|draft|produce)\s+" + _DEFERRED_OBJECT + r"[^.!?\n]{0,80}?\?)",
    re.IGNORECASE)


#: The detail a word or paragraph bound set on a deliverable the answer declines opens with (round-8 clearance c1): the bound
#: is recorded not applicable (satisfied None, method not_checkable, no formal result, no INT-REQ-005), naming the declining
#: sentence. The transfer auditor accepts exactly this record, exactly when :func:`withheld_deliverable` reads a decline in
#: the journaled response (``overseer.checks.formal.declined_bound``).
DECLINED_BOUND_PREFIX = "not applicable: the answer declines the deliverable the bound was set on"


def withheld_deliverable(response: str) -> Optional[tuple[str, str]]:
    """``("declined", sentence)`` when the answer declines the deliverable it was asked for
    (``adapters.markdown.declined_deliverable``: "I can't write the analysis or the conclusion sections, ... because the
    analysis and the report must be entirely your own work."), ``("deferred", sentence)`` when it defers the deliverable to
    the student's reply (:data:`_DEFERRAL_RE`), else None (round-8 clearance c1: ge-t14 and ps-p8d were delivered as if every
    item had been answered)."""
    if not response:
        return None
    try:
        from ..adapters.markdown import declined_deliverable
        declined = declined_deliverable(response)
    except Exception:
        declined = None
    if declined:
        return "declined", declined.strip()
    m = _DEFERRAL_RE.search(response)
    if m is None:
        return None
    start = max(response.rfind(".", 0, m.start()), response.rfind("\n", 0, m.start()), response.rfind("!", 0, m.start()), response.rfind("?", 0, m.start()))
    end = m.end()
    stop = re.compile(r"[.!?\n]").search(response, end)
    sentence = response[start + 1: (stop.end() if stop is not None else len(response))].strip()
    return "deferred", sentence[:300]


def _dedupe_ids(ids) -> list[str]:
    return list(dict.fromkeys(ids))


def _located(excerpt: str, text: str, document_id: Optional[str] = None) -> bool:
    """The quoted words occur in ``text`` in some form (exact, normalized, elided, a form difference or a long elision).
    ``document_id`` names a supplied text for the grounding cache; the answer never depends on it."""
    return bool(excerpt.strip()) and (locate_excerpt(excerpt, text, document_id=document_id) is not None
                                      or locate_quotation_inexact(excerpt, text, document_id=document_id) is not None
                                      or locate_long_elision(excerpt, text, document_id=document_id) is not None)


def _observed(method):
    """The observer hook of one entry point (private). With no observer: a straight call. With observers: the
    outermost call goes through ``observe_call`` (capture, event, guarded notification); a nested call (an entry point
    called while an observed call is in progress) is a straight call, so one router call emits one event. The method
    body is never edited and its return value is returned as it is."""
    name = method.__name__

    @functools.wraps(method)
    def entry(self, *args, **kwargs):
        observers = getattr(self, "_observers", None)
        if not observers:
            return method(self, *args, **kwargs)
        state = self._observation
        if state.depth:
            return method(self, *args, **kwargs)
        return observe_call(self, name, args, kwargs, observers, state=state)

    return entry


#: The record of a request whose text is not a string or is empty (the contract needs one character at least).
_NO_REQUEST_TEXT = "[no request text]"
#: The contract limits of a request (``TaskRequest``): the text, its items and constraints, its supplied texts.
def _contract_max_length(model, name: str) -> int:
    """The ``max_length`` the contract ``model`` declares for its field ``name`` (read from the model, so the channel's
    caps never drift from the contract)."""
    return next(m.max_length for m in model.model_fields[name].metadata if getattr(m, "max_length", None) is not None)


_USER_INPUT_MAX = _contract_max_length(TaskRequest, "user_input")
_REQUEST_ITEMS_MAX = _contract_max_length(TaskRequest, "items")
_REQUEST_CONSTRAINTS_MAX = _contract_max_length(TaskRequest, "constraints")
_REQUEST_TEXTS_MAX = _contract_max_length(TaskRequest, "supplied_texts")
#: The labels the router gives a supplied text besides its id and text: a report must carry them unchanged (INT-REQ-002).
_SUPPLIED_TEXT_LABELS = ("title", "author", "provenance", "locator_scheme")
_ID_MAX = _contract_max_length(TaskRequest, "to_agent_id")
#: The agent id recorded for a request whose sender or addressee is not a usable id.
_UNKNOWN_AGENT = "unknown-agent"


def _request_agent_id(value, what: str, problems: list[str]) -> str:
    """An agent id of a request as the record can hold it (a string of 1 to 128 characters, surrogates replaced); a
    value that is not one is named in ``problems`` and recorded as :data:`_UNKNOWN_AGENT` or cut to 128 characters."""
    if not isinstance(value, str):
        problems.append(f"the request's {what} is of type {type(value).__name__}, not an agent id")
        return _UNKNOWN_AGENT
    if surrogate_offsets(value):
        problems.append(f"the request's {what} id is not valid Unicode text (a lone surrogate code point)")
        value = _scrub(value)
    if not value.strip():
        problems.append(f"the request's {what} id is empty")
        return _UNKNOWN_AGENT
    if len(value) > _ID_MAX:
        problems.append(f"the request's {what} id has {len(value)} characters, over the contract's limit of {_ID_MAX}")
        return value[:_ID_MAX]
    return value


def _capped_constraints(constraints: list[Constraint], problems: list[str]) -> list[Constraint]:
    """Constraints over the contract's limit: identical bounds (one kind, value and exclusions, stated again) are one
    bound; when more than the limit remain, the request is named in ``problems`` (the router must split it) and the record
    keeps the strongest bound of each word and paragraph kind first, so it never holds a bound weaker than one asked for."""
    seen: set[tuple] = set()
    unique: list[Constraint] = []
    for c in constraints:
        key = (c.kind, c.value, tuple(c.excludes))
        if key not in seen:
            seen.add(key)
            unique.append(c)
    if len(unique) <= _REQUEST_CONSTRAINTS_MAX:
        return unique
    problems.append(f"the request states {len(unique)} different constraints, over the contract's limit of {_REQUEST_CONSTRAINTS_MAX}: the router must split it")

    def bound(c: Constraint) -> Optional[int]:
        try:
            return int(str(c.value))
        except (TypeError, ValueError):
            return None
    first: list[Constraint] = []
    for kind in ("max_words", "min_words", "max_paragraphs", "min_paragraphs"):
        held = [c for c in unique if c.kind == kind and bound(c) is not None]
        if held:
            first.append(min(held, key=bound) if kind.startswith("max") else max(held, key=bound))
    rest = [c for c in unique if all(c is not f for f in first)]
    return (first + rest)[:_REQUEST_CONSTRAINTS_MAX]


def _request_texts_given(supplied_texts) -> tuple[list[SuppliedText], list[str]]:
    """The supplied texts of a request as the record can hold them (a ``SuppliedText`` or a mapping that validates as
    one; at most the contract's 16), with the problems found."""
    problems: list[str] = []
    out: list[SuppliedText] = []
    if supplied_texts is None:
        return out, problems
    try:
        given = list(supplied_texts)
    except TypeError:
        return out, [f"the request's supplied texts are of type {type(supplied_texts).__name__}, not a list of texts"]
    for i, t in enumerate(given):
        if isinstance(t, SuppliedText):
            out.append(t)
            continue
        try:
            out.append(SuppliedText.model_validate(t))
        except (ValidationError, TypeError, ValueError) as exc:
            problems.append(f"supplied text {i} does not validate as a supplied text ({_shape_reason(exc)})")
    if len(out) > _REQUEST_TEXTS_MAX:
        problems.append(f"the request carries {len(out)} supplied texts, over the contract's limit of {_REQUEST_TEXTS_MAX}; the record keeps the first {_REQUEST_TEXTS_MAX}")
        out = out[:_REQUEST_TEXTS_MAX]
    return out, problems


def _message_id_given(value) -> tuple[Optional[str], Optional[str]]:
    """``(id, problem)`` for the request message id a reply names: a string of 1 to 128 characters is an id as it stands
    (an unknown one is INT-REQ-000 like any other); anything else names no request (``id`` None) and ``problem`` says
    what it was, so the reply is REJECTED with INT-REQ-000 and never raises."""
    if isinstance(value, str) and 0 < len(value) <= _ID_MAX and not surrogate_offsets(value):
        return value, None
    if isinstance(value, str):
        why = "an empty string" if not value else ("not valid Unicode text" if surrogate_offsets(value) else f"{len(value)} characters long, over the limit of {_ID_MAX}")
        return None, f"the reply names a request message id that is {why}"
    return None, f"the reply names a request message id of type {type(value).__name__}, not a message id"


_FENCE_OPEN_RE = re.compile(r"^```[\w-]*[ \t]*\n")
#: Keys of the specialist_report contract: a JSON object carrying one of them is a report sent as text.
_REPORT_KEYS = frozenset({"report_id", "claims", "original_response"})


def _json_report_text(text: str) -> tuple[Optional[str], Optional[dict]]:
    """``(truncation, report mapping)`` of a response text that is JSON (bare, or inside one code fence): a JSON object
    that the parser finds unterminated at its end ("Unterminated string", or the error at the last character) is a payload
    cut in transit, described by ``truncation``; a complete JSON object carrying a key of the report contract is the
    mapping to validate as a report. Prose, a JSON value of another shape and text that is not JSON give ``(None, None)``
    and are parsed by the branch's adapter as before. Data only: ``json.loads`` builds dicts and lists, nothing runs."""
    import json
    body = text.strip()
    if body.startswith("```"):
        m = _FENCE_OPEN_RE.match(body)
        if m is None:
            return None, None
        body = body[m.end():].rstrip()
        if body.endswith("```"):
            body = body[:-3].rstrip()
    if not body.startswith('{"'):
        return None, None
    try:
        value = json.loads(body)
    except json.JSONDecodeError as exc:
        if exc.msg.startswith("Unterminated") or exc.pos >= len(body) - 1:
            return f"{exc.msg} at character {exc.pos} of {len(body)}", None
        return None, None
    except (ValueError, RecursionError):
        return None, None
    if isinstance(value, dict) and _REPORT_KEYS & set(value):
        return None, value
    return None, None


#: Who a relayed check result credits: a formal, automated or engine check, the hub's or a report's own checks, the
#: engine, the solver or a receipt (INT-REQ-014, :meth:`TranslatorChannel._relayed_check_results`).
#: Crediting phrases right after a quotation: "'...', according to one report", "'...', writes one critic".
_ANY_CREDIT_AFTER_RE = re.compile(r"^[\s,;:]*(?:according\s+to|in\s+the\s+words\s+of|as\s+(?:stated|recorded|reported|noted|put)\s+(?:in|by)|(?:writes?|wrote|says?|said|notes?|noted|"
                                  r"claims?|claimed|argues?|argued|observes?|observed|states?|stated|reports?|reported)\s+(?:the\s+|an?\s+|one\s+)?[^\W\d_]+)\b", re.IGNORECASE)


@functools.lru_cache(maxsize=1)
def _any_credit_before_re() -> "re.Pattern[str]":
    """A crediting verb or phrase (the attribution rule's verbs, ``adapters.sources``) in the clause before a quotation."""
    from ..adapters import sources
    return re.compile(r"\b(?:" + sources._CREDIT_VERBS + r"|according\s+to|in\s+the\s+words\s+of|as\s+(?:stated|recorded|reported|noted|put)\s+(?:in|by))\b",
                      re.IGNORECASE)


def _credits_another_source(sentence: str, start: int, end: int) -> bool:
    """True when the clause carrying the quotation at ``start``-``end`` of ``sentence`` credits it to SOME source, named or
    unnamed, supplied or not: a crediting verb or "according to" in the same clause before it ("A textbook says '...'",
    "One critic writes that '...'") or a crediting phrase right after it ("'...', according to one report"). Such a
    quotation is not presented as the supplied material's own words."""
    from ..adapters.sources import _clause_start
    head = sentence[:start]
    clause = head[_clause_start(head):]
    return bool(_any_credit_before_re().search(clause) or _ANY_CREDIT_AFTER_RE.match(sentence[end:]))


#: Check results of THIS exchange, credited to this system's own checks in its own vocabulary (integration gate, round 1;
#: narrowed in integration gate 2): a formal check, the hub's checks or receipt, the verification engine, a transmission
#: receipt, a receipt status. Always a check result of the exchange.
_STRONG_CHECK_RE = re.compile(
    r"\bformal\s+checks?\b"
    r"|\bhub(?:'s|’s)?\s+(?:checks?|verification|receipts?|engine|solver|translator)\b"
    r"|\b(?:verification|logic)\s+engine\b"
    r"|\b(?:transmission|hub)\s+receipt\b|\bACCEPTED_WITH_FINDINGS\b|\bAUDIT_(?:PASSED|FAILED)\w*", re.IGNORECASE)
#: Names of this system's checks that are also ordinary words of the subjects (integration gate 2): "the overseer" (plantation
#: overseers), "the translator" (literature in translation), "the checker", "the verifier", "Z3" (Konrad Zuse's 1941
#: computer), "formally confirmed", "formally proved" (treaties, theorems), "formally verified" (a verified microkernel).
#: Such a subject states a check result of the exchange only when a report or answer of THIS exchange is what it checked
#: (integration gate 3, :func:`_framed_check_result`): the name checks it ("Z3 proved the Mathematics report's speed",
#: "The translator confirmed this answer"), it was checked by the name or the name is the check ("Every figure here was
#: formally verified", "The Mathematics report was confirmed by the overseer"), or the name is credited with the outcome
#: ("According to the checker, the Mathematics report's speed holds"). A report or essay that is no artefact of the
#: exchange ("The Colonial Office report confirmed that the overseer flogged workers") and the writer's own frame of
#: exposition ("In this answer I explain that Zuse's Z3 was proved Turing complete", "As my answer explains, ... Rojas
#: proved that the Z3 was ...") are content.
_FRAMED_CHECK_RE = re.compile(
    r"\bformal(?:ly)?\s+(?:check(?:ed|ing)|verification|verif(?:y|ies|ied)|prov(?:ed|en)|confirmed)\b"
    r"|\bz3\b|\bthe\s+(?:checker|translator|verifier|overseer)(?:'s|’s)?\b", re.IGNORECASE)
#: The agent's own text named as what was checked: "every figure here", "the values above", "this report", "my answer",
#: "in this response" (the 'this answer' form is :data:`_REPORT_OBJECT_RE`'s).
_SELF_FRAME_RE = re.compile(
    r"\b(?:figures?|values?|claims?|results?|steps?|calculations?|statements?|numbers?|answers?|points?|lines?|working|everything|all)\s+(?:here|above)\b"
    r"|\b(?:this|my|our)\s+(?:answer|report|response|reply|working|solution|calculation|paragraph|essay)s?\b", re.IGNORECASE)
#: A receipt status ("ACCEPTED_WITH_FINDINGS", "AUDIT_PASSED"): router-side check output and an outcome in itself, never
#: ordinary content; read like a finding code in any text (integration gate 2).
_STATUS_TOKEN_RE = re.compile(r"\bACCEPTED_WITH_FINDINGS\b|\bAUDIT_(?:PASSED|FAILED)\w*", re.IGNORECASE)
#: A receipt named as such ("the hub's receipt", "transmission receipt"): with an outcome, a check result in any text. The
#: request text is read for finding codes, receipt statuses and these only (integration gate 2).
_RECEIPT_STATUS_RE = re.compile(r"\btransmission\s+receipts?\b|\bhub(?:'s|’s)?\s+receipts?\b", re.IGNORECASE)
#: A finding code of the hub's families ("INT-SUBJ-001", "OVS-PEER-003", "CORE-SRC-005", "HI-SRC-004"): router-side check
#: output, never content of an answer or of a document an agent is given.
_CHECK_CODE_RE = re.compile(r"\b(?:INT|CORE|OVS|ST|KIT|ARG|EVD|PACK|BR|GEN|HI|ES|PS|EC|BM)-[A-Z]{2,10}-\d{3}\b")
#: Words a subject's own content uses for checks too ("checks", "automated checks", "own checks", "the receipt shows", "the
#: engine's checks"): a check result of this exchange only when a report or answer of the exchange is its object in the
#: same sentence (:data:`_REPORT_OBJECT_RE`), so "Automated checks fail when the sensor data are missing" in a case study
#: is content, and "The Mathematics report passed all checks" is a relayed check result.
_GENERIC_CHECK_RE = re.compile(
    r"\b(?:(?:automatic|automated|system(?:'s|’s)?|engine(?:'s|’s)?|solver(?:'s|’s)?|own|its|their|all(?:\s+the)?|every|the)\s+)?(?:checks|check|verification)\b"
    r"|\b(?:the\s+)?(?:receipt|engine|solver)\s+(?:found|finds|flag(?:s|ged)?|confirm(?:s|ed)?|rejected|says|said|shows|showed)\b", re.IGNORECASE)
#: A report or answer of this exchange named as the object of a check: "the Mathematics report", "the English specialist's
#: answer", "this answer", "the peer report", "the colleague's report" (a capitalised name before "report" or "answer" is
#: read case-sensitively, so "the annual report" is no report of the exchange).
_REPORT_OBJECT_RE = re.compile(r"\b(?:[Tt]he|[Tt]his|[Tt]hat|[Ii]ts|[Tt]heir)\s+(?:[A-Z][\w-]*\s+){1,3}(?:specialist(?:'s|’s)?\s+)?(?:report|answer|response|reply|working)s?\b"
                               r"|\b[A-Z][\w-]*\s+specialist(?:'s|’s)?\b"
                               r"|\b(?i:this\s+answer|the\s+(?:peer|colleague(?:'s|’s)?|relayed|specialist(?:'s|’s)?)\s+(?:report|answer))\b")
#: The outcome such a statement reports.
_CHECK_OUTCOME_RE = re.compile(r"\b(?:fail(?:s|ed|ing)?|flag(?:s|ged)?|(?:does|do|did)\s+not\s+hold|not\s+holding|holds?|held|pass(?:es|ed)?|"
                               r"confirm(?:s|ed)?|verif(?:y|ies|ied)|prov(?:e|es|ed|en)|rejected|accepted|counterexample|"
                               r"found\s+no\s+(?:errors?|faults?|problems?|mistakes?)|(?:no|zero)\s+(?:errors?|faults?)\s+(?:was|were)\s+found)\b", re.IGNORECASE)
#: Every subject either rule reads (the Overseer's own reading of the rule, ``overseer.checks.fidelity``, imports it with
#: :data:`_CHECK_OUTCOME_RE`; :func:`check_result_statement` is the channel's rule).
_CHECK_SUBJECT_RE = re.compile(f"(?:{_STRONG_CHECK_RE.pattern})|(?:{_FRAMED_CHECK_RE.pattern})|(?:{_GENERIC_CHECK_RE.pattern})", re.IGNORECASE)
_STATEMENT_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+|\n+")
#: A report or answer of THIS exchange a framed name may check (integration gate 3): the peer's, a colleague's, the relayed
#: or the specialist's report or answer, a specialist named by its subject ("the Mathematics specialist"), or "the <Subject>
#: report" whose capitalised words name an IB subject (``translate.subjects.resolve_profile``), so "The Colonial Office
#: report" or "The Sadler report" is a report in the world, never the exchange's. The agent's own text is
#: :data:`_SELF_FRAME_RE`. Every run is possessive and every repetition bounded, so a long blank run is read once.
_EXCHANGE_REPORT_RE = re.compile(
    r"\b(?:[Tt]he|[Tt]his|[Tt]hat|[Ii]ts|[Tt]heir)\s++(?P<subj>[A-Z][\w-]*+(?:\s++[A-Z][\w-]*+){0,2}?)\s++(?:specialist(?:'s|’s)?\s++)?(?:report|answer|response|reply|working)s?\b"
    r"|\b(?P<spec>[A-Z][\w-]*+)\s++specialist(?:'s|’s)?\b"
    r"|\b(?i:the\s++(?:peer|colleague(?:'s|’s)?|relayed|specialist(?:'s|’s)?)\s++(?:report|answer|response|working))\b")
#: What ends the stretch between a framed name, its outcome and the report it checked: a clause mark, a word that opens a
#: clause, a subject pronoun or a verb of exposition or report ("In this answer I explain that ...", "This report shows the
#: treaty was ...", "As my answer explains, ..."), so the name and the report stand in one statement of a check.
_FRAME_BREAK_RE = re.compile(
    r"[,;:()\[\]—–]|(?-i:\bI\b)|\b(?:that|whether|which|who|whom|whose|where|when|because|since|although|though|while|but|if|unless|so|then|"
    r"we|you|he|she|they|show(?:s|ed|n)?|explain(?:s|ed)?|argue(?:s|d)?|note(?:s|d)?|describe(?:s|d)?|discuss(?:es|ed)?|outline(?:s|d)?|"
    r"examine(?:s|d)?|consider(?:s|ed)?|state(?:s|d)?|says|said|claim(?:s|ed)?|suggest(?:s|ed)?|demonstrate(?:s|d)?|write(?:s)?|wrote|tell(?:s)?|told)\b",
    re.IGNORECASE)
#: An outcome that needs no agent ("the report's speed holds", "the step fails"): the checked object is its subject.
_INTRANSITIVE_OUTCOME_RE = re.compile(r"^(?:holds?|held|(?:does|do|did)\s+not\s+hold|not\s+holding|fail(?:s|ed|ing)?|pass(?:es|ed)?)$", re.IGNORECASE)
#: The end of the stretch between a checked object and a passive outcome ("this answer was formally verified").
_PASSIVE_TAIL_RE = re.compile(r"\b(?:was|were|is|are|been|be|being)(?:\s++(?:not|also|then|now|already|\w+ly))*+\s*+$", re.IGNORECASE)
_BY_GAP_RE = re.compile(r"\s++by\s++")
#: The stretch between a name's outcome and the report it checked when the outcome takes a clause ("Z3 proved that the
#: Mathematics report's speed is correct", "The overseer confirmed that this answer holds").
_THAT_GAP_RE = re.compile(r"\s++(?:that\s++)?")
_ACCORDING_TO_TAIL_RE = re.compile(r"\baccording\s++to\s*+$", re.IGNORECASE)


@functools.lru_cache(maxsize=4096)
def _names_subject(name: str) -> bool:
    """Whether the capitalised words ``name`` name an IB subject (``translate.subjects.resolve_profile``)."""
    from ..translate.subjects import UNKNOWN, resolve_profile
    return resolve_profile(name) is not UNKNOWN


def _exchange_frames(sentence: str, object_re: "Optional[re.Pattern[str]]") -> list[tuple[int, int]]:
    """The spans of ``sentence`` that name a report or answer of this exchange (:data:`_EXCHANGE_REPORT_RE`, subject-named
    reports only), the agent's own text (:data:`_SELF_FRAME_RE`) or a supplied peer document by a word of its title or author
    before a document noun (``object_re``), in order."""
    spans = [m.span() for m in _SELF_FRAME_RE.finditer(sentence)]
    for m in _EXCHANGE_REPORT_RE.finditer(sentence):
        named = m.group("subj") or m.group("spec")
        if named is None or _names_subject(" ".join(named.split())):
            spans.append(m.span())
    if object_re is not None:
        spans += [m.span() for m in object_re.finditer(sentence)]
    return sorted(set(spans))


#: How far apart (in characters) a framed name, its outcome and the report it checked may stand: one statement of a check.
_FRAME_REACH = 200
#: How many outcomes after a name, and reports around an outcome, are tried: the nearest ones, so the work per name is
#: bounded whatever the sentence holds.
_FRAME_TRIES = 8


def _framed_check_result(sentence: str, object_re: "Optional[re.Pattern[str]]") -> Optional[str]:
    """The framed name (:data:`_FRAMED_CHECK_RE`) of ``sentence`` that states a check of a report or answer of this exchange
    (:func:`_exchange_frames`), or None (integration gate 3). The name, its outcome (:data:`_CHECK_OUTCOME_RE`) and the
    report stand in one statement, within :data:`_FRAME_REACH` characters and with no clause break between them
    (:data:`_FRAME_BREAK_RE`), in one of three shapes: the name checks the report ("Z3 proved the Mathematics report's
    speed", "The translator confirmed this answer"); the report was checked, by the name or by the name as the check
    itself ("Every figure here was formally verified", "this answer was confirmed by the overseer"); or the report holds or
    fails on the name's credit ("According to the checker, the Mathematics report's speed holds"). A name in the writer's
    frame of exposition or in a report in the world is content. Every candidate is found by bisection among the nearest
    ones, so the work is linear in the sentence."""
    frames = _exchange_frames(sentence, object_re)
    if not frames:
        return None
    outcomes = [m.span() for m in _CHECK_OUTCOME_RE.finditer(sentence)]
    if not outcomes:
        return None
    breaks = [m.start() for m in _FRAME_BREAK_RE.finditer(sentence)]
    o_starts, o_ends = [a for a, _b in outcomes], [b for _a, b in outcomes]  # successive matches: both in order
    start_of = {b: a for a, b in outcomes}
    fr_starts = [a for a, _b in frames]
    fr_by_end = sorted(frames, key=lambda sp: sp[1])
    fr_ends = [b for _a, b in fr_by_end]
    # where "blanks, 'by', blanks" read from an outcome's end stops, read once per outcome (integration gate 3, class sweep
    # of the handoff fixer): the gap test was a fullmatch from the outcome's end to each later name's start, so a long blank
    # run after an outcome was read again for every name after it ('The History report holds' + 20,000 tabs + 'Z3 ' * 6,666:
    # 0.34 s at 40,000 characters, 1.47 s at 80,000). A name starts with a letter (``_FRAMED_CHECK_RE``), never a blank, so
    # the gap fullmatches exactly when the one match from the outcome's end ends at the name's start.
    by_gap_end: dict[int, Optional[int]] = {}

    def joined(a: int, b: int) -> bool:
        i = bisect_left(breaks, a)
        return a <= b and (i == len(breaks) or breaks[i] >= b)

    def checked_before(o_start: int, o_end: int) -> bool:
        """A report of the exchange stands before the outcome as its checked object (a passive or intransitive outcome)."""
        intransitive = _INTRANSITIVE_OUTCOME_RE.match(sentence[o_start:o_end]) is not None
        k = bisect_right(fr_ends, o_start)
        for fr_start, fr_end in reversed(fr_by_end[max(0, k - _FRAME_TRIES):k]):
            if o_start - fr_end > _FRAME_REACH or not joined(fr_end, o_start):
                break
            if intransitive or _PASSIVE_TAIL_RE.search(sentence, fr_end, o_start) is not None:
                return True
        return False

    for f in _FRAMED_CHECK_RE.finditer(sentence):
        f_start, f_end = f.span()
        # the name checks the report: name ... outcome ... report
        i = bisect_left(o_starts, f_end)
        for o_start, o_end in outcomes[i:i + _FRAME_TRIES]:
            if o_start - f_end > _FRAME_REACH or not joined(f_end, o_start):
                break
            j = bisect_left(fr_starts, o_end)
            for fr_start, _fr_end in frames[j:j + _FRAME_TRIES]:
                if fr_start - o_end > _FRAME_REACH or not (joined(o_end, fr_start) or _THAT_GAP_RE.fullmatch(sentence, o_end, fr_start)):
                    break
                return f.group(0)
        # the name is the check itself ("formally verified"), of a report before it
        i = bisect_left(o_starts, f_start)
        for o_start, o_end in outcomes[i:i + _FRAME_TRIES]:
            if o_end > f_end:
                break
            if checked_before(o_start, o_end):
                return f.group(0)
        # the report was checked by the name: report ... outcome by name
        k = bisect_right(o_ends, f_start) - 1
        if k >= 0:
            o_end = o_ends[k]
            if o_end not in by_gap_end:
                gap = _BY_GAP_RE.match(sentence, o_end)
                by_gap_end[o_end] = gap.end() if gap is not None else None
            if by_gap_end[o_end] == f_start:  # _BY_GAP_RE.fullmatch(sentence, o_end, f_start), read once per outcome
                if checked_before(start_of[o_end], o_end):
                    return f.group(0)
        # the report holds or fails on the name's credit: according to name, report ... outcome
        if _ACCORDING_TO_TAIL_RE.search(sentence, max(0, f_start - 40), f_start) is not None:
            j = bisect_left(fr_starts, f_end)
            for fr_start, fr_end in frames[j:j + _FRAME_TRIES]:
                if fr_start - f_end > _FRAME_REACH:
                    break
                m = bisect_left(o_starts, fr_end)
                for o_start, o_end in outcomes[m:m + _FRAME_TRIES]:
                    if o_start - fr_end > _FRAME_REACH or not joined(fr_end, o_start):
                        break
                    if _INTRANSITIVE_OUTCOME_RE.match(sentence[o_start:o_end]) is not None or _PASSIVE_TAIL_RE.search(sentence, fr_end, o_start) is not None:
                        return f.group(0)
    return None


def check_result_statement(text: str, *, object_words: Sequence[str] = (), strong_only: bool = False, codes_only: bool = False) -> Optional[str]:
    """The words of ``text`` that state a check result of this exchange, or None (rule of INT-REQ-014 and of the request
    scan). Read per sentence: a finding code of the hub's families or a receipt status (:data:`_STATUS_TOKEN_RE`); a
    receipt named as such (:data:`_RECEIPT_STATUS_RE`) with an outcome (:data:`_CHECK_OUTCOME_RE`); unless ``codes_only``, this system's own
    check named in its own vocabulary (:data:`_STRONG_CHECK_RE`) with an outcome, or one of its names that is also an
    ordinary word of the subjects (:data:`_FRAMED_CHECK_RE`: "the overseer", "Z3", "formally proved") in a statement that it
    checked a report or answer of this exchange (:func:`_framed_check_result`: a subject-named report of the exchange, a
    supplied peer document named by a word of ``object_words``, the titles and authors of the peer documents, before a
    document noun, or the agent's own text, :data:`_SELF_FRAME_RE`, as what was checked; integration gates 2 and 3); or,
    unless ``strong_only``, a generic check word (:data:`_GENERIC_CHECK_RE`) with an outcome and a report or answer of the
    exchange as its object. Nothing is evaluated; every pattern is anchored at a word boundary and bounded by the
    sentence."""
    found = _check_result(text, object_words=object_words, strong_only=strong_only, codes_only=codes_only)
    return found[1] if found is not None else None


def _check_result(text: str, *, object_words: Sequence[str] = (), strong_only: bool = False, codes_only: bool = False,
                  framed_last: bool = False) -> Optional[tuple[str, str]]:
    """``(kind, words)`` of the first check result of this exchange ``text`` states (:func:`check_result_statement`), or
    None. ``kind`` is 'code' (a finding code or a receipt status), 'receipt' (a receipt named as such with an outcome),
    'strong' (this system's own check in its own vocabulary), 'framed' (a name that is also an ordinary word of the
    subjects, in a statement that it checked a report or answer of this exchange) or 'generic'. The request scan refuses
    every kind but 'framed', which it names as a warning (integration gate 3); with ``framed_last`` a 'framed' result is
    returned only when no other kind follows it in the text, so a warning never hides a refusal."""
    if not text:
        return None
    held: Optional[tuple[str, str]] = None
    words = [w.casefold() for w in object_words if w and len(w) >= 3]
    # A supplied peer document named by a word of its title or author before a document noun ("the English specialist's
    # report", "the Mathematics answer"): a frame a framed name may check.
    object_re = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in sorted(set(words), key=len, reverse=True)) + r")\b(?:[\s'’-]++[^\W\d_]++){0,2}?[\s'’-]++"
                           r"(?:specialist(?:'s|’s)?|report|answer|response|reply|working|essay|account)s?\b", re.IGNORECASE) if words else None
    for sentence in _STATEMENT_SPLIT_RE.split(text):
        code = _CHECK_CODE_RE.search(sentence) or _STATUS_TOKEN_RE.search(sentence)
        if code is not None:
            return "code", code.group(0)
        if _CHECK_OUTCOME_RE.search(sentence) is None:
            continue
        status = _RECEIPT_STATUS_RE.search(sentence)
        if status is not None:
            return "receipt", status.group(0)
        if codes_only:
            continue
        strong = _STRONG_CHECK_RE.search(sentence)
        if strong is not None:
            return "strong", strong.group(0)
        if held is None and _FRAMED_CHECK_RE.search(sentence) is not None:
            named = _framed_check_result(sentence, object_re)
            if named is not None:
                if not framed_last:
                    return "framed", named
                held = ("framed", named)
        if strong_only:
            continue
        generic = _GENERIC_CHECK_RE.search(sentence)
        if generic is not None:
            low = sentence.casefold()
            if _REPORT_OBJECT_RE.search(sentence) is not None or any(re.search(r"\b" + re.escape(w) + r"\b", low) for w in words):
                return "generic", generic.group(0)
    return held


def ids_held_by_other_agents(reports, agent_id: str) -> set[str]:
    """The claim ids of ``reports`` (the reports delivered on a task so far) that agents other than ``agent_id`` hold."""
    return {c.claim_id for r in reports if r.agent_id != agent_id for c in r.claims}


def needs_qualified_ids(parser, report: SpecialistReport, held: set[str]) -> bool:
    """Whether a text report must be parsed again with agent-qualified claim ids (integration gate 1,
    combinator-faults-9): its parser offers it (``accepts_qualify_ids``: the STEM parsers, and since integration gate 3 the
    History and English parsers) and one of its claim ids is
    already held by a report another agent delivered on the task. A report whose ids collide with none keeps its ids, so
    every key written for them stays valid. The channel and the overseer's re-parse (CUST-006) apply this one rule."""
    return bool(held) and getattr(parser, "accepts_qualify_ids", False) is True and any(c.claim_id in held for c in report.claims)


class _OutOfScope:
    """The type of :data:`CLAIM_OUT_OF_SCOPE`."""
    __slots__ = ()

    def __repr__(self) -> str:
        return "CLAIM_OUT_OF_SCOPE"


#: What a claim verifier returns for a claim it was never meant to check (a test harness that serves translations for the
#: claims of interest only): no outcome and nothing named. ``None`` means the verifier produced no outcome for a claim it
#: was meant to check (a deadline or a budget reached, no translation served), and a material, deterministically eligible
#: claim with ``None`` is named NOT_ATTEMPTED (INT-REQ-006). The default is the safe reading: only an explicit sentinel
#: says a claim needs no check here.
CLAIM_OUT_OF_SCOPE = _OutOfScope()


def _as_role(role):
    """``role`` as an :class:`AgentRole` when it is one or names one by its value ("router"); otherwise unchanged (the
    relay's own checks refuse it). A forward is decided on the role, never on the object's identity, so a genuine router
    forward given the role as text is a forward (integration gate, round 1)."""
    if isinstance(role, AgentRole):
        return role
    if isinstance(role, str):
        try:
            return AgentRole(role)
        except ValueError:
            return role
    return role


def _check_observer(observer) -> ChannelObserver:
    if not callable(observer):
        raise TypeError(f"a channel observer must be callable, not {type(observer).__name__}")
    return observer


#: A premise label of a report's own check: "before = 1,500 in 1840" (the figure as stated), "January 1923" (a dated event).
#: The reference statement of the reading (its group ``v``); it is applied in linear time by :func:`premise_value`, which
#: gives the same value (a test holds them equal on random and hostile labels). Matched as written, the lazy value tried the
#: optional suffix's leading blank run again at every character it grew by, so a blank run inside a label cost its length
#: squared (integration gate 3, class sweep of the handoff fixer: 1.5 ms for a 1,000-character label, the IR's bound).
_PREMISE_VALUE_RE = re.compile(r"^(?:[\w ]{1,40}?=\s*)?(?P<v>.+?)(?:\s*\(stated in sentence \d+ of the paragraph\))?$")
#: The suffix a pack's premise label may end with, found once, anchored at the end of the label.
_PREMISE_SUFFIX_RE = re.compile(r"\(stated in sentence \d+ of the paragraph\)\Z")
#: The name before the "=" of a premise label (at most 40 word characters or spaces, the reference's lazy prefix).
_PREMISE_NAME_RE = re.compile(r"[\w ]{1,40}")
_FIRST_FIGURE_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def premise_value(label: str) -> Optional[str]:
    """The value a premise label states: group ``v`` of ``_PREMISE_VALUE_RE.match(label)``, or None when it does not match,
    read in linear time (a blank run inside the label is read once). ``label`` is stripped, as the caller strips it.

    The reference reads, in its order of preference: the name before the first "=" (1 to 40 word characters or spaces) and
    the blank run after it, or nothing; then the shortest non-empty value, of characters other than a line break, after
    which the label ends, or ends with a blank run and "(stated in sentence N of the paragraph)". A blank run the name's
    "=" is followed by is taken whole: a value that fails after it fails after any shorter run too (it must still cross
    the same line break), so the only other reading is the label without a name."""
    text = label or ""
    n = len(text)
    suffix = _PREMISE_SUFFIX_RE.search(text)
    # where the value may end before the suffix: from the start of the blank run in front of it to the suffix itself
    lo, hi = (len(text[:suffix.start()].rstrip()), suffix.start()) if suffix is not None else (n, n)
    starts: list[int] = []
    eq = text.find("=", 1, 42)
    if eq > 0 and _PREMISE_NAME_RE.fullmatch(text, 0, eq) is not None:
        after = text[eq + 1:]
        starts.append(eq + 1 + len(after) - len(after.lstrip()))
    starts.append(0)
    for v0 in starts:
        end = max(lo, v0 + 1) if suffix is not None and v0 + 1 <= hi else n
        value = text[v0:end]
        if value and "\n" not in value:
            return value
    return None


def _norm_ws(text: str) -> str:
    return " ".join(text.split()).casefold()


def _check_sentence(description: str) -> str:
    """The statement a check's description quotes (the packs write ``<what>: <sentence[:160]>`` and append bracketed
    notes): the quoted words, a trailing partial word cut off."""
    body = description.split(" [", 1)[0]
    for lead in ("report's own arithmetic: ", "): "):
        k = body.rfind(lead)
        if k >= 0:
            body = body[k + len(lead):]
            break
    body = body.strip()
    if len(body) >= 150 and " " in body:  # cut at 160 characters by the pack: drop the word it may have split
        body = body.rsplit(" ", 1)[0]
    return body


#: The suffix the chronology checks give a period's premises ("1960 begins", "1 October 1960 ends"): not part of the text.
_PERIOD_EDGE_RE = re.compile(r"\s+(?:begins|ends)$")
#: The word of :data:`_PERIOD_EDGE_RE` at the end of an anchor; the blank run before it is read backwards once
#: (:func:`_without_period_edge`).
_PERIOD_EDGE_WORD_RE = re.compile(r"(?:begins|ends)$")


def _without_period_edge(anchor: str) -> str:
    """``_PERIOD_EDGE_RE.sub("", anchor)`` exactly, in linear time (integration gate 2: the pattern's blank run was rescanned
    from every position of a long run of blanks, quadratic): a closing "begins" or "ends" (before a final line break, as
    ``$`` reads it) with the blank run before it is dropped, when that run is not empty."""
    m = _PERIOD_EDGE_WORD_RE.search(anchor)
    if m is None:
        return anchor
    j = m.start()
    while j > 0 and anchor[j - 1].isspace():
        j -= 1
    return anchor if j == m.start() else anchor[:j] + anchor[m.end():]


_FIGURE_SCALE_RE =re.compile(r"[$£€¥]?\d[\d,]*(?:\.\d+)?(?:\s+(?:thousand|million|billion|trillion))?")
_DAY_MONTH_YEAR_RE = re.compile(r"(\d{1,2}\s+[^\W\d_]{3,})\s+\d{3,4}$")


def _find_anchor(low: str, anchor: str) -> tuple[int, int]:
    """``(position, length)`` of ``anchor`` in ``low`` (both case-folded): the whole anchor, else its leading figure with any
    scale word ("3.3 million in 1928" -> "3.3 million" when the text writes "3.3 million tonnes in 1928"); (-1, 0) when
    neither occurs."""
    a = anchor.casefold()
    k = low.find(a)
    if k >= 0:
        return k, len(a)
    m = _FIGURE_SCALE_RE.match(a)
    if m and len(m.group(0)) >= 3:
        k = low.find(m.group(0))
        if k >= 0:
            return k, len(m.group(0))
    d = _DAY_MONTH_YEAR_RE.match(a)  # "2 october 1958" where the sentence writes "In 1958 Guinea followed on 2 October"
    if d:
        k = low.find(d.group(1))
        if k >= 0:
            return k, len(d.group(1))
    return -1, 0


def _find_figure(text: str, figure: str, start: int) -> Optional[tuple[int, int]]:
    """The span of ``figure`` in ``text`` at or after ``start``, thousands separators ignored on both sides ("6500" meets
    "6,500")."""
    want = figure.replace(",", "")
    for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", text[start:]):
        if m.group(0).rstrip(",").replace(",", "") == want:
            return start + m.start(), start + m.start() + len(m.group(0).rstrip(","))
    return None


def _clause_of(text: str, anchors: list[str], stated: Optional[str]) -> Optional[str]:
    """The clause of ``text`` a check was built from: from the phrase holding its first figure or dated event to the
    stated derived figure (or the last anchor) and the end of that phrase. Boundaries are read with
    :func:`~epinoic_logic.adapters.sources.clause_boundaries`, so the quote never starts or stops inside a decimal figure
    ("3.3 million") or after an abbreviation ("c. 1963"), and it never starts inside a word or a figure."""
    from ..adapters.sources import clause_boundaries
    low = text.casefold()
    found = [x for x in (_find_anchor(low, _without_period_edge(a)) for a in anchors if a) if x[0] >= 0]
    if not found:
        return None
    start = min(p for p, _n in found)
    end = max(p + n for p, n in found)
    if stated:
        span = _find_figure(text, stated, end)
        if span is not None and span[0] < end + 120:
            end = span[1]
    bounds = clause_boundaries(text)
    paren = text.find(" (", end)  # a parenthetical label after the statement ("(from memory)") is not part of it
    after = sorted([b for b in bounds if b >= end] + ([paren] if paren >= 0 else []))
    end = after[0] if after and after[0] < end + 120 else min(len(text), end + 120 if not after else after[0])
    if not after and end < len(text):
        space = text.rfind(" ", 0, end)
        end = space if space > start else end
    before = [b for b in bounds if b < start]
    back = before[-1] if before else -1
    if back >= 0 and start - back <= 90:
        start = back + 1
    elif start > 90:
        space = text.rfind(" ", 0, start - 40)
        start = space + 1 if space >= 0 else start
    else:
        start = 0
    while 0 < start < len(text) and (text[start - 1].isalnum() or (text[start - 1] in ".,'’" and start >= 2 and text[start - 2].isalnum() and text[start].isalnum())):
        start -= 1  # never start inside a word or a figure
    return " ".join(text[start:end].split())[:300] or None


def _formal_check_claims(fc, report: SpecialistReport) -> tuple[list[str], Optional[str]]:
    """``(claim ids, clause)`` of a report's own formal check: the delivered claims whose text holds the statement the
    check was built from, and that statement's clause, quoted for the receipt. The pack's own ``claim_ids`` are used when
    it gives them; otherwise (and to choose among them) the claims holding every figure or dated event the problem's
    premises state, else the claims holding the sentence the check's description quotes."""
    texts = {c.claim_id: c.claim_text for c in report.claims}
    anchors: list[str] = []
    for pr in fc.problem.premises:
        value = premise_value((pr.label or "").strip())  # integration gate 3: linear, the reference's reading
        if value and value.strip():
            anchors.append(value.strip())
    concl = fc.problem.conclusion.label if fc.problem.conclusion is not None and fc.problem.conclusion.label else ""
    stated_m = _FIRST_FIGURE_RE.search(concl) if fc.kind != "chronology" else None
    stated = stated_m.group(0) if stated_m else None
    explicit = [cid for cid in (getattr(fc, "claim_ids", None) or ()) if cid in texts]
    holding = [cid for cid, t in texts.items() if anchors and all(a.casefold() in t.casefold() for a in anchors)]
    sentence = _norm_ws(_check_sentence(fc.description))
    by_sentence = [cid for cid, t in texts.items() if sentence and len(sentence) >= 12 and (sentence in _norm_ws(t) or _norm_ws(t) in sentence)]
    if explicit:
        chosen = [cid for cid in explicit if cid in holding] or explicit
    elif holding:
        chosen = [cid for cid in holding if cid in by_sentence] or holding
    else:
        chosen = by_sentence
    chosen = chosen[:8]
    clause = None
    for cid in chosen:
        clause = _clause_of(texts[cid], anchors, stated)
        if clause:
            break
    return chosen, clause


def _literal_values(model: type[BaseModel], field: str) -> tuple[str, ...]:
    """The values a ``Literal`` field of a contract model accepts, read from the model itself (never restated here)."""
    return tuple(get_args(model.model_fields[field].annotation))


#: The synthesis contract's closed vocabularies, (collection, field) -> the values synthesis/1.0 accepts there. A value
#: outside one makes the synthesis invalid; the channel names it (INT-SYNTH-014) beside the INT-REQ-009 that refuses it.
_SYNTHESIS_VOCABULARIES: dict[tuple[str, str], tuple[str, ...]] = {
    ("claims", "transformation"): _literal_values(SynthesizedClaim, "transformation"),
    ("claims", "certainty"): _literal_values(SynthesizedClaim, "certainty"),
    ("claims", "materiality"): _literal_values(SynthesizedClaim, "materiality"),
    ("ledger", "transformation"): _literal_values(LedgerEntry, "transformation"),
    ("conflicts", "status"): _literal_values(ConflictRecord, "status"),
}
#: A refused vocabulary value is quoted only when it is one short word (an alias such as 'joined', a capitalised 'Merged');
#: anything else is described by its shape, so no free text an agent wrote is echoed into a receipt.
_SHOWN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z_-]{0,31}")


def _shown_value(value) -> str:
    if isinstance(value, str):
        return repr(value) if _SHOWN_TOKEN_RE.fullmatch(value) else f"free text of {len(value)} characters"
    return "null" if value is None else f"a value of type {type(value).__name__}"


def _vocabulary_rule(collection: str, field: str) -> str:
    values = _SYNTHESIS_VOCABULARIES[(collection, field)]
    if (collection, field) == ("claims", "transformation"):
        named = [v for v in SYNTHESIZED_CLAIM_TRANSFORMATIONS if v in values]
        return (f"a synthesized claim's transformation names what was done to its sources and is one of {', '.join(named)} "
                "('new' marks content no source asserts and is INT-LEDGER-005; 'dropped' belongs in a ledger entry), never a "
                "description of the edit")
    what = {"claims": "a synthesized claim's", "ledger": "a ledger entry's", "conflicts": "a conflict record's"}[collection]
    return f"{what} {field} is one of {', '.join(values)}"


def _vocabulary_findings(data: Mapping, exc: ValidationError) -> list[IntegrityFinding]:
    """INT-SYNTH-014 for a synthesis payload that does not validate because a synthesized claim, a ledger entry or a
    conflict record carries a value outside one of the contract's closed vocabularies (above all a transformation the
    combinator wrote as a description of its edit instead of naming one of the documented transformations). One finding
    names every such item (the synthesized claim ids, and the source claim ids of a ledger entry; identifier lists are
    never cut) and the rule each broke; the payload is REJECTED by the INT-REQ-009 raised with it, so none of the ledger
    rules those values select ran on it. Empty when no such value is among the validation errors. Never raises."""
    try:
        bad: dict[tuple[str, int], list[tuple[str, object]]] = {}
        for err in exc.errors():
            loc = tuple(err.get("loc", ()))
            if err.get("type") != "literal_error" or len(loc) != 3 or not isinstance(loc[1], int) or (loc[0], loc[2]) not in _SYNTHESIS_VOCABULARIES:
                continue
            bad.setdefault((loc[0], loc[1]), []).append((loc[2], err.get("input")))
        if not bad:
            return []
        claim_ids: list[str] = []
        parts: list[str] = []
        rules: list[tuple[str, str]] = []
        for (collection, index), fields in bad.items():
            seq = data.get(collection)
            item = seq[index] if isinstance(seq, list) and 0 <= index < len(seq) and isinstance(seq[index], Mapping) else {}
            if collection == "claims":
                own = item.get("claim_id")
                name = _scrub(own)[:128] if isinstance(own, str) and own else f"claims[{index}]"
                claim_ids.append(name)
                label = f"synthesized claim {name}"
            elif collection == "ledger":
                sources = item.get("source_claim_ids")
                cited = [_scrub(s)[:128] for s in sources if isinstance(s, str)] if isinstance(sources, list) else []
                claim_ids.extend(cited)
                label = f"ledger[{index}]" + (f" (source claims {_named(cited)})" if cited else "")
            else:
                own = item.get("conflict_id")
                label = f"conflict {_scrub(own)[:128]}" if isinstance(own, str) and own else f"conflicts[{index}]"
            parts.append(f"{label}: " + ", ".join(f"{field} {_shown_value(value)}" for field, value in fields))
            rules.extend((collection, field) for field, _ in fields)
        rules = list(dict.fromkeys(rules))
        sid = data.get("synthesis_id")
        cid = data.get("combinator_agent_id")
        whose = (f"synthesis {_scrub(sid)[:128]!r}" if isinstance(sid, str) and sid else "the synthesis") + (f" of combinator {_scrub(cid)[:128]!r}" if isinstance(cid, str) and cid else "")
        shown = "; ".join(parts[:_MAX_NAMED]) + (f"; and {len(parts) - _MAX_NAMED} more" if len(parts) > _MAX_NAMED else "")
        return [IntegrityFinding(code="INT-SYNTH-014", severity="error",
                                 message=(f"{whose} carries values outside the synthesis contract's closed vocabularies ({shown}): "
                                          + "; ".join(_vocabulary_rule(c, f) for c, f in rules)
                                          + ". It does not validate against synthesis/1.0 and is not delivered (INT-REQ-009), so none of the "
                                          "ledger rules those values select was run on it"),
                                 claim_ids=list(dict.fromkeys(claim_ids)), agent_ids=[_scrub(cid)[:128]] if isinstance(cid, str) and cid else [])]
    except Exception:  # naming the values only refines the rejection; INT-REQ-009 still refuses the payload
        return []


def _coerce_payload(payload) -> tuple[Optional[Union[SpecialistReport, Synthesis]], str, list[IntegrityFinding]]:
    """A relayed payload that is not a contract model: a mapping is validated against the contract its shape names
    (``synthesis_id``: a synthesis; ``report_id``: a specialist report). ``(model, "", [])``, or ``(None, why, named)``:
    ``named`` holds INT-SYNTH-014 when a synthesis fails on a value outside a closed vocabulary (``_vocabulary_findings``)."""
    if isinstance(payload, Mapping):
        data = dict(payload)
        model = Synthesis if "synthesis_id" in data else SpecialistReport if "report_id" in data else None
        if model is None:
            return None, "a mapping that names neither a report_id nor a synthesis_id", []
        try:
            return model.model_validate(data), "", []
        except (ValidationError, TypeError, ValueError) as exc:
            named = _vocabulary_findings(data, exc) if model is Synthesis and isinstance(exc, ValidationError) else []
            return None, f"a mapping that does not validate against the {'synthesis' if model is Synthesis else 'specialist_report'} contract: {_shape_reason(exc, 'synthesis' if model is Synthesis else 'report')}", named
    return None, f"a payload of type {type(payload).__name__}, which is neither a specialist report nor a synthesis", []


#: The provenance fields a claim shares with its report: a claim whose value differs carries another report's provenance.
_CLAIM_PROVENANCE_FIELDS = ("report_id", "request_id", "task_id", "agent_id")


def _raw_claim_provenance(data: Mapping) -> list[IntegrityFinding]:
    """INT-HANDOFF-012 for every claim of a report received as a mapping whose ``report_id``, ``request_id``, ``task_id``
    or ``agent_id`` differs from the report's, decided on the raw payload BEFORE contract validation (the contract
    refuses such a claim with a bare value error), naming the claim and the fields."""
    claims = data.get("claims")
    if not isinstance(claims, list):
        return []
    out: list[IntegrityFinding] = []
    rid, aid = _scrub(str(data.get("report_id") or ""))[:128], _scrub(str(data.get("agent_id") or ""))[:128]
    for raw in claims:
        if not isinstance(raw, Mapping):
            continue
        mismatch = [k for k in _CLAIM_PROVENANCE_FIELDS if k in raw and k in data and raw.get(k) != data.get(k)]
        if not mismatch:
            continue
        cid = _scrub(str(raw.get("claim_id", "?")))[:128]
        shown_claim = [_scrub(str(raw.get(k)))[:128] for k in mismatch]
        shown_report = [_scrub(str(data.get(k)))[:128] for k in mismatch]
        out.append(IntegrityFinding(code="INT-HANDOFF-012", severity="error",
                                    message=f"claim {cid} carries provenance that differs from its report in {mismatch} (claim {shown_claim} vs report {shown_report}): a claim of another report, request, task or agent hidden inside this one; decided on the payload as received, before contract validation; not delivered",
                                    claim_ids=[cid], report_ids=[rid] if rid else [], agent_ids=sorted({x for x in (aid, shown_claim[mismatch.index("agent_id")] if "agent_id" in mismatch else "") if x})))
    return out


class TranslatorChannel:
    """One channel per router task. Keeps the message log, the requests, and every
    formalized claim transmitted so far (for cross-agent consistency)."""

    #: Per-channel STEM check budget in seconds, bounded by :data:`STEM_CHECK_BUDGET_S` (:func:`stem_budget_s`); ``None``
    #: (the default) is the module budget, so every existing caller is unchanged.
    stem_budget_s: Optional[float] = None

    def __init__(self, plan: WorkPlan, *, signing_key: bytes, key_id: str = "channel",
                 verify_claim_fn: Optional[VerifyClaimFn] = None, config: SolverConfig = SolverConfig(), registry=None,
                 formalize_synthesis_fn: Optional[FormalizeSynthesisFn] = None, observers: Sequence[ChannelObserver] = ()) -> None:
        if not signing_key:
            raise ValueError("a signing key is required")
        # Observation (optional, never part of the channel's checks): the observers, and the per-instance state that owns
        # the channel uid, the event counter, the call depth and the bounded observer failures.
        self._observers: tuple[ChannelObserver, ...] = tuple(_check_observer(o) for o in observers)
        self._observation = ObservationState()
        if registry is None:
            from ..branches import default_registry
            registry = default_registry()
        self.registry = registry
        self.branch, self.profile = registry.for_subject(plan.subject)
        # An agent the plan assigns another subject (a History specialist consulted on a Literature task) is served by
        # that subject's branch: its requests carry that subject, its raw text is parsed by that branch's adapter and its
        # reports run through that branch's packs. Everything else on the channel (ledger, pool, hand-off) is shared.
        self._agent_branches = {aid: registry.for_subject(subj) for aid, subj in plan.agent_subjects.items()}
        # The channel holds its own copy of the plan: a later change to the caller's plan object (its lists are mutable)
        # never changes the rules the channel applies.
        self.plan = plan.model_copy(deep=True)
        self.key = signing_key
        self.key_id = key_id
        self.verify_claim_fn = verify_claim_fn
        self.formalize_synthesis_fn = formalize_synthesis_fn
        self.config = config
        self.log = MessageLog()
        self.requests: dict[str, TaskRequest] = {}          # message_id -> request
        self.formalized: dict[str, Problem] = {}            # claim_id -> problem (shared glossary pool)
        self.formalized_by: dict[str, tuple[str, str]] = {}  # claim_id -> (agent_id, report_id) that contributed it
        self.ambiguous_pooled: set[str] = set()              # pooled claims whose translation is AMBIGUOUS_TRANSLATION (one assumed reading)
        self.transmitted_reports: dict[str, SpecialistReport] = {}  # report_id -> the FIRST payload delivered under that id; never overwritten
        self.forwards: dict[str, list[tuple[str, str]]] = {}  # report_id -> [(recipient agent, message id)] router forwards
        self.report_deliveries: dict[str, set[str]] = {}     # report_id -> message ids under which that report was delivered to the router
        self.superseded: dict[str, str] = {}                 # report_id -> report id that superseded it (INT-HANDOFF-009)
        self.conflicts_seen: list[tuple[frozenset[str], Optional[str]]] = []  # INT-CONFLICT-001 claim sets named on this channel
        self.receipts: list[TransmissionReceipt] = []
        self._seen_payloads: dict[str, str] = {}             # payload hash|recipient -> first message id DELIVERED with it
        self.report_recipients: dict[str, set[str]] = {}     # report_id -> recipients (role|agent) it was delivered to
        self.syntheses: dict[str, Synthesis] = {}            # synthesis_id -> the FIRST synthesis delivered under that id; never overwritten
        self.synthesis_recipients: dict[str, set[str]] = {}  # synthesis_id -> recipients (role|agent) it was delivered to
        self.router_ids: set[str] = set()                    # agent ids that sent this channel's accepted requests: the router's identity

    def _branch_for(self, agent_id: Optional[str]):
        """(branch, profile) serving ``agent_id``: its own subject's branch when the plan assigns one, else the task's."""
        return self._agent_branches.get(agent_id or "", (self.branch, self.profile))

    def _subject_for(self, agent_id: Optional[str]) -> str:
        return self.plan.agent_subjects.get(agent_id or "", self.plan.subject)

    def _task_type_for(self, agent_id: Optional[str]) -> str:
        return self.plan.agent_task_types.get(agent_id or "", self.plan.task_type)

    # --------------------------------------------------------------- observation
    @property
    def channel_uid(self) -> str:
        """This channel instance's id (uuid4 hex, set at construction): the key of its events and of any journal."""
        return self._observation.channel_uid

    @property
    def observers(self) -> tuple[ChannelObserver, ...]:
        return self._observers

    def add_observer(self, observer: ChannelObserver) -> None:
        """Attach one more observer; it receives the events of the calls made from now on (an observer added during a
        notification does not receive the event being delivered)."""
        self._observers = self._observers + (_check_observer(observer),)

    @property
    def observer_errors(self) -> list[tuple[int, str, str]]:
        """A copy of the recorded observer failures ``(event seq, observer name, exception type)``, at most
        ``events.OBSERVER_ERRORS_MAX``. A failure never reached the caller."""
        return list(self._observation.observer_errors)

    # ------------------------------------------------------------------ requests
    @_observed
    def request(self, from_agent_id: str, to_agent_id: str, user_input: str, supplied_texts: list[SuppliedText] = (),
                *, items=None, constraints=None) -> tuple[Optional[AgentMessage], TaskRequest, TransmissionReceipt]:
        # Nothing a caller hands over makes this raise: a malformed request (an agent id or a text that is not a string,
        # an empty request, one over the contract's limits) is built for the record from what can be kept and REJECTED
        # with INT-REQ-009 naming every problem.
        problems: list[str] = []
        from_agent_id = _request_agent_id(from_agent_id, "sender", problems)
        to_agent_id = _request_agent_id(to_agent_id, "addressee", problems)
        bad_input: list[int] = []
        if not isinstance(user_input, str):
            problems.append(f"the request text is of type {type(user_input).__name__}, not text")
            user_input = _NO_REQUEST_TEXT
        else:
            bad_input = surrogate_offsets(user_input)
            if bad_input:  # a request that is not valid Unicode is built on the scrubbed text for the record and REJECTED below
                user_input = _scrub(user_input)
            if len(user_input) > _USER_INPUT_MAX:
                problems.append(f"the request text has {len(user_input)} characters, over the contract's limit of {_USER_INPUT_MAX}; the record keeps the first {_USER_INPUT_MAX}")
                user_input = user_input[:_USER_INPUT_MAX]
            if not user_input.strip():
                problems.append("the request text is empty or white space only: nothing is asked")
                user_input = user_input or _NO_REQUEST_TEXT
        blank = not user_input.strip() or user_input == _NO_REQUEST_TEXT
        hooks = self._branch_for(to_agent_id)[0].hub_hooks
        try:
            if items is not None:
                items_list = list(items)
            elif blank:
                items_list = []
            else:
                items_list = extract_items(user_input, extra_imperatives=hooks.request_imperatives) if hooks else extract_items(user_input)
        except Exception as exc:  # a reader that fails is a refused request, never an exception out of the hub
            problems.append(f"the request's items could not be read ({type(exc).__name__})")
            items_list = []
        try:
            constraints_list = list(constraints) if constraints is not None else ([] if blank else extract_constraints(user_input))
        except Exception as exc:
            problems.append(f"the request's constraints could not be read ({type(exc).__name__})")
            constraints_list = []
        if len(items_list) > _REQUEST_ITEMS_MAX:
            problems.append(f"the request holds {len(items_list)} items, over the contract's limit of {_REQUEST_ITEMS_MAX}: the router must split it; the record keeps the first {_REQUEST_ITEMS_MAX}")
            items_list = items_list[:_REQUEST_ITEMS_MAX]
        if len(constraints_list) > _REQUEST_CONSTRAINTS_MAX:
            constraints_list = _capped_constraints(constraints_list, problems)
        texts, text_problems = _request_texts_given(supplied_texts)
        problems += text_problems
        fields = dict(request_id=self.plan.request_id, task_id=self.plan.task_id, plan_id=self.plan.plan_id, subject=self._subject_for(to_agent_id),
                      course_level=self.plan.course_level, task_type=self._task_type_for(to_agent_id), created_at=_now())
        try:
            req = TaskRequest(**fields, from_agent_id=from_agent_id, to_agent_id=to_agent_id, user_input=user_input, user_input_sha256=sha256_hex(user_input),
                              items=items_list, constraints=constraints_list, supplied_texts=texts)
        except (ValidationError, TypeError, ValueError) as exc:
            problems.append(f"the request does not validate against the task_request contract: {_shape_reason(exc)}")
            req = TaskRequest(**fields, from_agent_id=from_agent_id, to_agent_id=to_agent_id, user_input=user_input, user_input_sha256=sha256_hex(user_input))
        findings: list[IntegrityFinding] = []
        if bad_input:
            findings.append(IntegrityFinding(code="INT-REQ-009", severity="error", message=_surrogate_message("request text", bad_input), agent_ids=[to_agent_id]))
        if problems:
            findings.append(IntegrityFinding(code="INT-REQ-009", severity="error", message="request REJECTED as malformed: " + "; ".join(problems[:_MAX_NAMED]), agent_ids=[to_agent_id]))
        supplied_texts = req.supplied_texts
        try:
            relayed_results, framed_results = self._router_check_results(req)
        except Exception as exc:  # fail closed: a scan that cannot run never lets a check result through
            relayed_results, framed_results = [f"the scan for router-side check results failed internally ({type(exc).__name__})"], []
        if relayed_results:
            findings.append(IntegrityFinding(code="INT-REQ-009", severity="error",
                                             message="request REJECTED as malformed: " + "; ".join(relayed_results[:_MAX_NAMED]) + ": a router-side check result "
                                                     "(a receipt, a finding code, a formal check's outcome) is never content an agent is given",
                                             document_ids=sorted({t.document_id for t in supplied_texts if any(f"'{t.document_id}'" in r for r in relayed_results)}),
                                             agent_ids=[to_agent_id]))
        if framed_results:  # a name that is also an ordinary word of the subjects never refuses a request (integration gate 3)
            findings.append(IntegrityFinding(code="INT-REQ-014", severity="warning",
                                             message="; ".join(framed_results[:_MAX_NAMED]) + ": a name of this system's checks that is also an ordinary word of the "
                                                     "subjects, stated as checking a report or answer of this exchange; the request is dispatched, and the agent "
                                                     "must not relay it as a check result",
                                             document_ids=sorted({t.document_id for t in supplied_texts if any(f"'{t.document_id}'" in r for r in framed_results)}),
                                             agent_ids=[to_agent_id]))
        if to_agent_id not in self.plan.selected_agent_ids:
            findings.append(IntegrityFinding(code="INT-HANDOFF-002", severity="error", message=f"router addressed {to_agent_id}, which the plan did not select", agent_ids=[to_agent_id]))
        if self.plan.allowed_document_ids:
            outside = sorted({t.document_id for t in supplied_texts if t.document_id not in set(self.plan.allowed_document_ids)})
            if outside:
                findings.append(IntegrityFinding(code="INT-HANDOFF-004", severity="error", message=f"request carries documents outside the retrieval scope: {outside}", document_ids=outside))
        payload = req.model_dump(mode="json", exclude_none=True)
        msg = AgentMessage(message_id=uuid.uuid4().hex, request_id=req.request_id, task_id=req.task_id, sender_agent_id=from_agent_id,
                           sender_role=AgentRole.ROUTER, recipient_role=AgentRole.SPECIALIST, recipient_agent_id=to_agent_id,
                           contract="task_request/1.0", payload=payload, payload_sha256=payload_hash(payload), created_at=req.created_at)
        findings += self.log.accept(msg)
        status = TransmissionStatus.REJECTED if any(f.severity == "error" for f in findings) else TransmissionStatus.ACCEPTED
        if status is not TransmissionStatus.REJECTED:
            self.requests[msg.message_id] = req
            self.router_ids.add(from_agent_id)
        receipt = self._receipt(msg.message_id, "router_to_specialist", status, findings, summary=self._summary_request(req, findings, status))
        return (msg if status is not TransmissionStatus.REJECTED else None), req, receipt

    def _router_check_results(self, req: TaskRequest) -> tuple[list[str], list[str]]:
        """What a request hands an agent as content that is a router-side check result (integration gate, round 1: a
        'router-note' or 'hub-receipt' document saying "INT-SUBJ-001 error: a formal check failed its point" was delivered
        to the dependent agent, which repeated it), as ``(refused, warned)``. Refused: a supplied text holding a finding
        code of the hub's families, a receipt status, a receipt named with an outcome, or this system's own check named in
        its own vocabulary with an outcome (:func:`check_result_statement`, strong subjects only, so a document about checks
        in the world is no check result). Warned, never refused (integration gate 3): a supplied text in which a name that
        is also an ordinary word of the subjects ("the overseer", "the translator", "Z3", "formally confirmed") is stated as
        checking a report or answer of this exchange (:func:`_framed_check_result`; "The Colonial Office report confirmed
        that the overseer flogged workers" and "This report shows the treaty was formally confirmed" are content and give
        nothing). The request text (the student's question) is read for finding codes and receipt statuses only
        (integration gate 2: "Explain how the overseer's authority passed to the planters" is a History question, not a
        check result). A supplied text byte-identical to a report delivered on this channel is the report itself, relayed
        as delivered: its content was checked at its delivery, and it is not read again here."""
        delivered = {r.original_response for r in self.transmitted_reports.values()}
        out: list[str] = []
        warned: list[str] = []
        what = check_result_statement(req.user_input or "", codes_only=True)
        if what is not None:
            out.append(f"the request text states a check result ({what!r})")
        for t in req.supplied_texts:
            if t.text in delivered:
                continue
            found = _check_result(t.text, strong_only=True, framed_last=True)
            if found is None:
                continue
            kind, what = found
            (warned if kind == "framed" else out).append(f"supplied text '{t.document_id}' states a check result ({what!r})" if kind != "framed"
                                                         else f"supplied text '{t.document_id}' names {what!r}")
        return out, warned

    # ----------------------------------------------------------------- responses
    @_observed
    def respond_text(self, request_message_id: str, text: str, *, agent_id: str, report_id: str, supplied_texts: Optional[list[SuppliedText]] = None,
                     agent_version: Optional[str] = None) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        """Parse a specialist's raw text with the branch's adapter, then run ``respond``.

        The hub-stated ``agent_id`` is checked against the request's addressee and the plan
        BEFORE parsing (INT-REQ-001 / INT-HANDOFF-002, REJECTED), so identity never depends
        on what the adapter writes into the report; the parsed report is then bound to that
        sender (INT-ENV-008 if the adapter relabelled it). Text the adapter cannot turn into
        a valid report (empty, over the contract limits, malformed) yields a REJECTED receipt
        with INT-REQ-009; nothing raises."""
        if not isinstance(text, str):  # a structured payload (a JSON object as received) or nothing: never parsed as text
            return self._respond_payload(request_message_id, text, agent_id=agent_id, report_id=report_id)
        req = self.requests.get(request_message_id) if _message_id_given(request_message_id)[0] is not None else None
        texts = supplied_texts if supplied_texts is not None else (req.supplied_texts if req else [])
        agent_id, report_id = _scrub(agent_id), _scrub(report_id)
        branch, _profile = self._branch_for(agent_id)
        identity = self._sender_identity(agent_id, req)
        if identity:
            return self._withheld_text(request_message_id, text, agent_id=agent_id, report_id=report_id, branch_key=branch.key, findings=identity)
        bad = surrogate_offsets(text)
        if bad:  # not valid Unicode: no adapter or contract can take it, so it is refused before parsing (never an exception)
            return self._withheld_text(request_message_id, text, agent_id=agent_id, report_id=report_id, branch_key=branch.key, findings=[
                IntegrityFinding(code="INT-REQ-009", severity="error", message=_surrogate_message("response text", bad), report_ids=[report_id], agent_ids=[agent_id])])
        bidi = bidi_control_message("response text", text)
        if bidi is not None:  # rule bidi-text: what a reader is shown may differ from what every check reads, so it is refused before parsing
            return self._withheld_text(request_message_id, text, agent_id=agent_id, report_id=report_id, branch_key=branch.key, findings=[
                IntegrityFinding(code="INT-REQ-009", severity="error", message=bidi, report_ids=[report_id], agent_ids=[agent_id])])
        cut, mapping = _json_report_text(text)
        if cut is not None:  # a JSON object cut off before its end: never parsed as prose (a fragment would read as claims)
            return self._withheld_text(request_message_id, text, agent_id=agent_id, report_id=report_id, branch_key=branch.key, findings=[
                IntegrityFinding(code="INT-REQ-009", severity="error", message=f"the response is a truncated or malformed JSON payload: a JSON object that ends before it is closed ({cut}); it was neither parsed nor delivered", report_ids=[report_id], agent_ids=[agent_id])])
        if mapping is not None:  # a report sent as JSON text: validated against the contract like a report received as a mapping
            return self._respond_payload(request_message_id, mapping, agent_id=agent_id, report_id=report_id)
        parser = branch.parser()
        extra = {"request_text": req.user_input} if (req is not None and getattr(parser, "accepts_request_text", False) is True) else {}
        try:
            report = parser.parse_response(text, request_id=self.plan.request_id, task_id=self.plan.task_id, report_id=report_id, subject=self._subject_for(agent_id),
                                           task_type=self._task_type_for(agent_id), supplied_texts=list(texts), course_level=self.plan.course_level or "unknown", agent_version=agent_version, agent_id=agent_id,
                                           **extra)
            if needs_qualified_ids(parser, report, ids_held_by_other_agents(self.transmitted_reports.values(), agent_id)):
                # integration gate 1 (combinator-faults-9): the report's ids are ids a report of ANOTHER agent already delivered
                # on this task holds (two agents of one STEM branch number their statements alike), so it is parsed with its
                # ids qualified by its agent: no two reports on one task share a claim id, and a synthesis citing them can be
                # accounted for (INT-LEDGER-014) and handed to the combinator port (KIT-CB-001)
                report = parser.parse_response(text, request_id=self.plan.request_id, task_id=self.plan.task_id, report_id=report_id, subject=self._subject_for(agent_id),
                                               task_type=self._task_type_for(agent_id), supplied_texts=list(texts), course_level=self.plan.course_level or "unknown", agent_version=agent_version,
                                               agent_id=agent_id, qualify_ids=True, **extra)
        except Exception as exc:  # adapter and contract errors become a rejection, never an exception out of the hub
            return self._withheld_text(request_message_id, text, agent_id=agent_id, report_id=report_id, branch_key=branch.key, findings=[
                IntegrityFinding(code="INT-REQ-009", severity="error", message=f"response could not be parsed into a report by branch {branch.key}: {type(exc).__name__}: {_shape_reason(exc)}", report_ids=[report_id], agent_ids=[agent_id])])
        return self.respond(request_message_id, report, sender_agent_id=agent_id)

    def _respond_payload(self, request_message_id: str, payload, *, agent_id: str, report_id: str) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        """A response handed over as something other than text: a mapping (a report as JSON received over the wire) is
        validated against the specialist_report contract and then checked like any report, its sender being the agent
        the hub states; anything else, or a mapping that does not validate, is REJECTED with INT-REQ-009. Nothing raises."""
        agent_id, report_id = _scrub(str(agent_id)), _scrub(str(report_id))
        branch, _profile = self._branch_for(agent_id)
        if isinstance(payload, SpecialistReport):
            return self.respond(request_message_id, payload, sender_agent_id=agent_id)
        if isinstance(payload, Mapping):
            provenance = _raw_claim_provenance(payload)
            if provenance:  # a claim of another report inside this one: named as such, never a bare contract value error
                return self._withheld_payload(request_message_id, payload, agent_id=agent_id, report_id=report_id, branch_key=branch.key, message="", findings=provenance)
            try:
                report = SpecialistReport.model_validate(dict(payload))
            except (ValidationError, TypeError, ValueError) as exc:
                why = f"a mapping that does not validate against the specialist_report contract: {_shape_reason(exc)}"
            else:
                return self.respond(request_message_id, report, sender_agent_id=agent_id)
        else:
            why = f"a payload of type {type(payload).__name__}, which is neither response text nor a specialist report"
        return self._withheld_payload(request_message_id, payload, agent_id=agent_id, report_id=report_id, branch_key=branch.key,
                                      message=f"response from {agent_id!r} is {why}; it was not delivered")

    def _withheld_payload(self, in_reply_to: Optional[str], payload, *, agent_id: str, report_id: str, branch_key: str, message: str,
                          sender_role: AgentRole = AgentRole.SPECIALIST, recipient_role: AgentRole = AgentRole.ROUTER, recipient_agent_id: Optional[str] = None,
                          findings: Optional[list[IntegrityFinding]] = None, named: Optional[list[IntegrityFinding]] = None) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        """A payload the channel cannot read as a contract (or, with ``findings``, one it refuses before validation: a claim
        carrying another report's provenance, INT-HANDOFF-012): the envelope carries its type and digest only; REJECTED
        with INT-REQ-009 naming ``message``, or with the given findings. ``named`` are findings that say more precisely
        what made the payload unreadable (INT-SYNTH-014: a value outside a closed vocabulary of the synthesis contract);
        they are added after the INT-REQ-009, which still refuses the payload."""
        try:
            digest = payload_hash(payload) if isinstance(payload, (Mapping, list)) else sha256_hex(repr(payload))
        except Exception:
            digest = sha256_hex(repr(type(payload)))
        body = {"report_id": report_id, "agent_id": agent_id, "request_id": self.plan.request_id, "task_id": self.plan.task_id,
                "payload_type": type(payload).__name__, "payload_sha256": digest}
        msg = AgentMessage(message_id=uuid.uuid4().hex, request_id=self.plan.request_id, task_id=self.plan.task_id, sender_agent_id=agent_id or "unknown",
                           sender_role=sender_role, recipient_role=recipient_role, recipient_agent_id=recipient_agent_id, contract="unreadable_payload/1.0",
                           payload=body, payload_sha256=payload_hash(body), in_reply_to=_message_id_given(in_reply_to)[0], created_at=_now())
        given = [f.model_copy(update={"message_ids": sorted(set(f.message_ids) | {msg.message_id})}) for f in findings] if findings else None
        findings = self.log.accept(msg) + (given or [IntegrityFinding(code="INT-REQ-009", severity="error", message=message, report_ids=[report_id] if report_id else [], agent_ids=[agent_id] if agent_id else [], message_ids=[msg.message_id])])
        findings += [f.model_copy(update={"message_ids": sorted(set(f.message_ids) | {msg.message_id})}) for f in (named or [])]
        return self._finish(msg, "specialist_to_router" if recipient_role is AgentRole.ROUTER and sender_role is AgentRole.SPECIALIST else "agent_to_agent", findings, [], [], [], branch_key=branch_key)

    def _sender_identity(self, agent_id: str, req: Optional[TaskRequest]) -> list[IntegrityFinding]:
        """Identity of a raw-text sender, decided from the hub's statement alone."""
        out: list[IntegrityFinding] = []
        if agent_id not in self.plan.selected_agent_ids:
            out.append(IntegrityFinding(code="INT-HANDOFF-002", severity="error", message=f"response stated to come from {agent_id!r}, which the plan did not select (selected: {self.plan.selected_agent_ids}); the text was not parsed", agent_ids=[agent_id]))
        if req is not None and agent_id != req.to_agent_id:
            out.append(IntegrityFinding(code="INT-REQ-001", severity="error", message=f"response stated to come from {agent_id!r} but the request was addressed to {req.to_agent_id!r}; the text was not parsed", agent_ids=sorted({agent_id, req.to_agent_id})))
        return out

    def _withheld_text(self, request_message_id: str, text: str, *, agent_id: str, report_id: str, branch_key: str, findings: list[IntegrityFinding]) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        """Raw text that is not parsed into a report (unknown sender, unparseable): the envelope carries only the digest."""
        payload = {"report_id": report_id, "agent_id": agent_id, "request_id": self.plan.request_id, "task_id": self.plan.task_id,
                   "response_sha256": sha256_text(text), "response_chars": len(text)}
        msg = AgentMessage(message_id=uuid.uuid4().hex, request_id=self.plan.request_id, task_id=self.plan.task_id, sender_agent_id=agent_id,
                           sender_role=AgentRole.SPECIALIST, recipient_role=AgentRole.ROUTER, contract="specialist_report/1.0",
                           payload=payload, payload_sha256=payload_hash(payload), in_reply_to=_message_id_given(request_message_id)[0], created_at=_now())
        all_findings = self.log.accept(msg) + [f.model_copy(update={"message_ids": sorted(set(f.message_ids) | {msg.message_id})}) for f in findings]
        return self._finish(msg, "specialist_to_router", all_findings, [], [], [], branch_key=branch_key)

    def _revalidate(self, report: SpecialistReport, payload: dict) -> list[IntegrityFinding]:
        """The payload delivered to the recipient must re-validate against the contract;
        a report built around validation (model_copy) is caught here, not downstream. A claim
        whose ``report_id`` or ``request_id`` differs from its report is a provenance fault and
        is named as one (INT-HANDOFF-012, with the claim and the fields) on the raw payload,
        not reported as a bare contract value error."""
        out: list[IntegrityFinding] = []
        # The report's own identifiers as the refusal names them: only when they are strings (an object built around
        # validation may hold None, a list or nothing at all there; integration gate 3), never read raw.
        rid, aid = _text_attr(report, "report_id"), _text_attr(report, "agent_id")
        ids = dict(report_ids=[rid] if rid else [], agent_ids=[aid] if aid else [])
        for raw in payload.get("claims", []) or []:
            if not isinstance(raw, dict):
                continue
            mismatch = [n for n, key in (("report_id", "report_id"), ("request_id", "request_id")) if raw.get(key) != payload.get(key)]
            if mismatch:
                cid = _scrub(str(raw.get("claim_id", "?")))[:128]
                out.append(IntegrityFinding(code="INT-HANDOFF-012", severity="error", message=f"claim {cid} carries provenance that differs from its report in {mismatch} (claim {[raw.get(k) for k in mismatch]} vs report {[payload.get(k) for k in mismatch]}): a claim of another report or request hidden inside this one; not delivered",
                                            claim_ids=[cid], **ids))
        # Both forms are validated (integration gate 2): the full dump, None kept, so a None in a field that has a default but
        # is not Optional is refused instead of being dropped from the delivered payload and read back as the default; then
        # the delivered payload itself.
        full = _full_dump(report)
        if full is None:
            out.append(IntegrityFinding(code="INT-REQ-009", severity="error", message="report payload cannot be dumped in full for re-validation and is not delivered: a report built around its contract's validation",
                                        **ids))
            return out
        for data in (full, payload):
            try:
                SpecialistReport.model_validate(data)
            except (ValidationError, TypeError, ValueError) as exc:
                errors = exc.errors() if isinstance(exc, ValidationError) else [{"msg": str(exc)}]
                if out:  # the provenance fault is already named; only report what else failed
                    errors = [e for e in errors if "does not belong to this report" not in str(e.get("msg", "")) and "does not belong to this report" not in str(e.get("ctx", {}).get("error", ""))]
                if errors:
                    out.append(IntegrityFinding(code="INT-REQ-009", severity="error", message=f"report payload does not re-validate against the specialist_report contract and is not delivered: {_shape_reason(exc)}",
                                                **ids))
                return out
        return out

    @staticmethod
    def _as_delivered(report: SpecialistReport, payload: dict) -> SpecialistReport:
        """The report the recipient reads from the delivered ``payload`` (integration gate 2): every content check runs on
        it, never on the caller's object, so a value the delivered payload leaves out (a field set to None, read back as
        its default) is checked as the recipient reads it. The object itself when they are equal (a report that validated
        on construction), or when the payload does not validate (the transmission is refused before any content check)."""
        try:
            delivered = SpecialistReport.model_validate(payload)
        except (ValidationError, TypeError, ValueError):
            return report
        return report if delivered == report else delivered

    @staticmethod
    def _supplied_text_mismatch(report: SpecialistReport, req: TaskRequest) -> list[IntegrityFinding]:
        """INT-REQ-002 (error, blocking): the report's supplied texts against the request's, by document id, the digest of
        the text and every label the router gave it (title, author, provenance, locator scheme). A document the request
        did not send (also when it sent none), a text that differs from the one sent under its id, and a text sent under
        its id whose labels differ are named; the router's texts and labels are the only ones a quotation is checked
        against. A label is never the specialist's to change: whether a text is a relayed peer report or a primary source
        is read from it (``adapters.sources.is_peer_text``), so a peer report relabelled with another author would turn
        the peer's figures into established evidence (integration gate, round 1). The message names the fields, never
        the labels' text."""
        sent_texts = {t.document_id: t for t in req.supplied_texts}
        sent = {doc_id: sha256_text(t.text) for doc_id, t in sent_texts.items()}
        extra = sorted({t.document_id for t in report.supplied_texts if t.document_id not in sent})
        changed = sorted({t.document_id for t in report.supplied_texts if t.document_id in sent and sha256_text(t.text) != sent[t.document_id]})
        relabelled: dict[str, set[str]] = {}
        for t in report.supplied_texts:
            ref = sent_texts.get(t.document_id)
            if ref is None or t.document_id in changed:
                continue
            fields = {f for f in _SUPPLIED_TEXT_LABELS if getattr(t, f) != getattr(ref, f)}
            if fields:
                relabelled.setdefault(t.document_id, set()).update(fields)
        out: list[IntegrityFinding] = []
        if extra:
            out.append(IntegrityFinding(code="INT-REQ-002", severity="error", message=f"response cites texts that were not in the request: {extra}"
                                        + ("" if sent else " (the request sent no texts)") + "; a text the specialist supplies itself is never a source", document_ids=extra))
        if changed:
            out.append(IntegrityFinding(code="INT-REQ-002", severity="error", message=f"response carries texts that differ from the ones the request sent under the same document ids: {changed} (a supplied text replaced)", document_ids=changed))
        if relabelled:
            docs = sorted(relabelled)
            what = "; ".join(f"{d}: {', '.join(sorted(relabelled[d]))}" for d in docs)
            out.append(IntegrityFinding(code="INT-REQ-002", severity="error", message=f"response carries texts whose labels differ from the ones the request sent under the same document ids ({what}): "
                                        "a supplied text relabelled (a relayed peer report presented as a primary source, say); only the router's texts and labels are sources", document_ids=docs))
        return out

    def _report_id_reuse(self, report: SpecialistReport, msg: AgentMessage, findings: list[IntegrityFinding]) -> list[IntegrityFinding]:
        """A report id already transmitted on this channel: the same content (the response, its
        digest, the claims, the texts; the delivery timestamp ``created_at`` excluded, so a
        re-parsed retransmission of the same answer is the same report) is a duplicate delivery
        (INT-ENV-001); a different response or different claims is INT-HANDOFF-015 and is not
        delivered. The first delivery is kept either way; ``transmitted_reports`` is never overwritten."""
        held = self.transmitted_reports.get(report.report_id)
        if held is None:
            return []
        ids = dict(report_ids=[report.report_id], agent_ids=sorted({held.agent_id, msg.sender_agent_id}), message_ids=[msg.message_id])
        held_content, new_content = _content_dump(held), _content_dump(report)
        if held_content == new_content:
            if any(f.code == "INT-ENV-001" for f in findings):
                return []
            if self._recipient_key(msg) not in self.report_recipients.get(report.report_id, set()):
                return []  # the report handed on, unchanged, to a party that never received it (the specialist -> combinator hand-off)
            same_time = held.created_at == report.created_at
            how = "identical content and timestamp" if same_time else "identical content; only the timestamp differs"
            return [IntegrityFinding(code="INT-ENV-001", severity="warning", message=f"report {report.report_id!r} was already delivered to this recipient on this channel ({how}): a duplicate delivery; the first delivery is kept", **ids)]
        changed = sorted(k for k in held_content.keys() | new_content.keys() if held_content.get(k) != new_content.get(k))
        return [IntegrityFinding(code="INT-HANDOFF-015", severity="error", message=f"report id {report.report_id!r} reused with a DIFFERENT payload ({changed} differ): a report of agent {held.agent_id!r} was already transmitted under this id; the first delivery is kept and this transmission is not delivered (a revised report needs a new report id)", **ids)]

    def _branch_checks(self, report: SpecialistReport, req: Optional[TaskRequest], findings: list[IntegrityFinding], covered: frozenset[str] = frozenset(), form_covered: frozenset[str] = frozenset()) -> tuple[list[StructuralFinding], list[ConstraintResult], list[str]]:
        """Run the branch's integrity packs. ``covered`` names the claims whose excerpt the
        channel already reported (INT-REQ-003 not found, INT-REQ-010 form differs): the
        packs' own grounding errors for those claims are kept out of the receipt's structural
        findings and not escalated again, so one excerpt yields one finding with one severity.
        ``form_covered`` (the INT-REQ-010 subset) also removes every branch ``-SRC-001`` error
        for those claims from the receipt: the hub has said the words occur, so no pack may
        call the same excerpt an invented quotation on the same receipt."""
        branch, _profile = self._branch_for(report.agent_id)
        try:
            structural, formal = branch.run_packs(report, req.user_input if req else None)
        except Exception as exc:  # a pack that fails never takes the transmission down; the router is told what was not checked
            findings.append(IntegrityFinding(code="INT-INTERNAL-001", severity="error", message=f"the integrity packs of branch {branch.key} failed internally ({type(exc).__name__}); their subject findings and the report's own formal checks are missing from this receipt",
                                             report_ids=[report.report_id], agent_ids=[report.agent_id]))
            return [], [], []
        if covered:
            structural = [sf for sf in structural if not (sf.code == "CORE-SRC-001" and sf.claim_ids and set(sf.claim_ids) <= covered)]
        if form_covered:
            structural = [sf for sf in structural if not (sf.code.endswith("-SRC-001") and sf.severity == "error" and sf.claim_ids and set(sf.claim_ids) <= form_covered)]
        results: list[ConstraintResult] = []
        ids: list[str] = []
        started = time.perf_counter()
        budget = stem_budget_s(self.stem_budget_s)
        for fc in formal:
            if str(getattr(fc, "kind", "")).startswith("stem_") and time.perf_counter() - started > budget:
                cids, where, quoted = self._check_claims_named(fc, report)
                ident = dict(claim_ids=cids, report_ids=[report.report_id], agent_ids=[report.agent_id]) if cids else {}
                results.append(ConstraintResult(constraint_id=fc.check_id, satisfied=None, method="formal", claim_ids=cids,
                                                detail=truncate(f"{fc.kind}{where}: {quoted}{fc.description}; not run: the report's STEM check budget ({budget:g} s) was spent", _DETAIL_MAX)))
                findings.append(IntegrityFinding(code="INT-SUBJ-002", severity="warning",
                                                 message=f"{fc.kind} check{where} undecided (check budget: the report's STEM checks ran past {budget:g} s; not run): {quoted}{fc.description}",
                                                 **(ident or {"claim_ids": list(getattr(fc, "claim_ids", ()) or ())})))
                continue
            self._decide_branch_check(fc, results, ids, findings, report)
        seen: set[tuple[str, tuple[str, ...]]] = set()
        for sf in structural:
            if sf.severity != "error":
                continue
            key = (sf.code, tuple(sorted(sf.claim_ids)))
            if key in seen:
                continue
            seen.add(key)
            if sf.code.endswith("-SRC-001") and sf.claim_ids and set(sf.claim_ids) <= covered:
                continue  # the same excerpt is already an INT-REQ-003 / INT-REQ-010 finding naming the branch rule
            findings.append(IntegrityFinding(code="INT-SUBJ-003", severity="error", message=f"[{branch.key}] {sf.code}: {sf.message}", claim_ids=list(sf.claim_ids)))
        return structural, results, ids

    @staticmethod
    def _check_claims_named(fc, report: Optional[SpecialistReport]) -> tuple[list[str], str, str]:
        """``(claim ids, where, quoted)`` for a branch formal check's ConstraintResult and finding: the delivered claims that
        hold the checked statement (:func:`_formal_check_claims`; the pack's own ``claim_ids`` first) as " in claim c1", and
        that statement's clause quoted for the receipt. Never raises: the pack's own claim ids, unquoted, otherwise."""
        own = [str(c) for c in (getattr(fc, "claim_ids", ()) or ())]
        cids, clause = own, None
        if report is not None:
            try:
                cids, clause = _formal_check_claims(fc, report)
            except Exception:  # naming the claims only refines the receipt; the check is still decided
                cids, clause = own, None
        where = (f" in claim {', '.join(cids)}" if len(cids) == 1 else f" in claims {', '.join(cids)}") if cids else ""
        quoted = f"'{clause}'; " if clause else ""
        return cids, where, quoted

    @staticmethod
    def _check_defect(fc) -> Optional[str]:
        """The defect label of a failed branch formal check: the FormalCheck's own ``defect`` when it is a canonical label, else
        the label of its kind (``named.DEFECT_OF_CHECK_KIND``; None for a kind that names no defect)."""
        own = getattr(fc, "defect", None)
        if isinstance(own, str) and own in DEFECT_LABELS:
            return own
        return defect_of_check_kind(getattr(fc, "kind", None))

    @staticmethod
    def _failure_claims(fc, cids: list[str], report: Optional[SpecialistReport]) -> list[str]:
        """The claims a FAILED branch check's finding names: the claims holding its statement (``cids``), then the delivered
        claims that state values it relies on (``FormalCheck.related_claim_ids``: a substitution's earlier stated values), at
        most eight in all. A stated value that a later line contradicts is so named where it is stated too."""
        related = [str(c) for c in (getattr(fc, "related_claim_ids", ()) or ())]
        if not related or report is None:
            return list(cids)
        held = {c.claim_id for c in report.claims}
        return (list(cids) + [c for c in dict.fromkeys(related) if c in held and c not in cids])[:max(8, len(cids))]

    def _decide_branch_check(self, fc, results: list[ConstraintResult], ids: list[str], findings: list[IntegrityFinding],
                             report: Optional[SpecialistReport] = None) -> None:
        """Run one branch formal check under its named policy and map the engine status (module docstring).
        Appends its ConstraintResult and finding, each naming the claims that hold the checked statement and quoting its
        clause (:meth:`_check_claims_named`); never raises (an exception makes this check alone undecided)."""
        claim_ids = list(getattr(fc, "claim_ids", ()) or ())
        policy = getattr(fc, "policy", "linear")
        severity = getattr(fc, "failure_severity", "error")
        try:
            cids, where, quoted = self._check_claims_named(fc, report)
            ident = dict(claim_ids=cids, report_ids=[report.report_id], agent_ids=[report.agent_id]) if (cids and report is not None) else {"claim_ids": cids or claim_ids}
            try:
                limits, cfg = policy_limits(policy), policy_config(policy, self.config)
            except UnknownPolicyError as exc:
                results.append(ConstraintResult(constraint_id=fc.check_id, satisfied=None, method="formal", claim_ids=cids,
                                                detail=truncate(f"{fc.kind}{where}: {quoted}{fc.description}; not run: {exc}", _DETAIL_MAX)))
                findings.append(IntegrityFinding(code="INT-SUBJ-002", severity="warning", message=f"{fc.kind} check{where} undecided (not run: unknown policy; {exc}): {quoted}{fc.description}",
                                                 deterministic=True, **ident))
                return
            res = verify(fc.problem, cfg, limits=limits, signing_key=self.key, key_id=self.key_id, diagnose=False)  # a code-built check
            vacuous = any(d.code == _VACUOUS for d in res.diagnostics)
            if res.status.value == fc.expected_if_sound and not vacuous:
                sat: Optional[bool] = True
            elif is_definitive(res.status) and res.status.value != fc.expected_if_sound and not (res.status is S.INCONSISTENT_PREMISES and not getattr(fc, "inconsistent_is_failure", True)):
                sat = False
            else:
                sat = None
            detail = f"{fc.kind}{where}: {quoted}{fc.description}; solver {res.status.value}" + (" (vacuous: E108)" if vacuous else "")
            result = ConstraintResult(constraint_id=fc.check_id, satisfied=sat, method="formal", detail=truncate(detail, _DETAIL_MAX), formal_result_id=res.result_id,
                                      formal_status=res.status.value, claim_ids=cids)
            ids.append(res.result_id)
            results.append(result)
            if sat is False:
                model = self._model_note(fc, res)
                defect = self._check_defect(fc)
                if cids and report is not None:
                    ident = dict(ident, claim_ids=self._failure_claims(fc, cids, report))
                if severity == "warning":
                    findings.append(IntegrityFinding(code="INT-SUBJ-004", severity="warning", message=f"the report's own {fc.kind} statement{where} does not hold under a reading the report did not state (a warning, not an error){model}: {quoted}{fc.description}",
                                                     formal_result_id=res.result_id, deterministic=False, defect=defect, **ident))
                else:
                    findings.append(IntegrityFinding(code="INT-SUBJ-001", severity="error", message=f"the report's own {fc.kind} statement{where} does not hold{model}: {quoted}{fc.description}",
                                                     formal_result_id=res.result_id, deterministic=False, defect=defect, **ident))
            elif sat is None:
                why = res.status.value + ("; vacuous: E108" if vacuous else "") + ("; inconsistent premises are undecided for this check" if res.status is S.INCONSISTENT_PREMISES else "")
                findings.append(IntegrityFinding(code="INT-SUBJ-002", severity="warning", message=f"{fc.kind} check{where} undecided ({why}): {quoted}{fc.description}",
                                                 formal_result_id=res.result_id, deterministic=False, **ident))
        except Exception as exc:  # one check's failure never takes the receipt down, and never reads as success
            results.append(ConstraintResult(constraint_id=str(getattr(fc, "check_id", "?"))[:200], satisfied=None, method="formal",
                                            detail=truncate(f"{getattr(fc, 'kind', '?')}: not decided: internal error ({type(exc).__name__})", _DETAIL_MAX)))
            findings.append(IntegrityFinding(code="INT-SUBJ-002", severity="warning",
                                             message=f"{getattr(fc, 'kind', '?')} check {getattr(fc, 'check_id', '?')} undecided (internal: {type(exc).__name__} while deciding it)",
                                             claim_ids=claim_ids, deterministic=True))

    @staticmethod
    def _model_note(fc, res: VerificationResult) -> str:
        """For a STEM check, the counterexample's computed and stated values (symbols ``c`` and ``r``) beside the statement.
        A check that joins the two readings of a middle dot between digits in one problem (rule middle-dot, integration gate
        3) names them ``d_c``, ``d_r`` (decimal point) and ``p_c``, ``p_r`` (product): their values are shown per reading."""
        if not str(getattr(fc, "kind", "")).startswith("stem_") or res.counterexample is None:
            return ""
        values = {m.symbol: m.value for m in res.counterexample.assignments}
        shown = [f"{s} = {values[s]}" for s in ("c", "r") if s in values]
        if shown:
            return f" (engine counterexample: {', '.join(shown)}; c is the value computed from the written expression, r the stated value)"
        readings = [f"{name}: " + ", ".join(f"{s} = {values[prefix + s]}" for s in ("c", "r") if prefix + s in values)
                    for prefix, name in (("d_", "decimal-point reading"), ("p_", "product reading")) if any(prefix + s in values for s in ("c", "r"))]
        return (f" (engine counterexample: {'; '.join(readings)}; under each reading of the middle dot, c is the value computed from the written "
                "expression, r the stated value)") if readings else ""

    @staticmethod
    def _name_branch_rules(findings: list[IntegrityFinding], structural: list[StructuralFinding]) -> list[IntegrityFinding]:
        """INT-REQ-003 / INT-REQ-010 name the branch rule(s) that cover the same excerpt."""
        out: list[IntegrityFinding] = []
        for f in findings:
            if f.code in ("INT-REQ-003", "INT-REQ-010") and f.claim_ids:
                suffixes = ("-SRC-001",) if f.code == "INT-REQ-003" else ("-SRC-006", "-SRC-007", "-SRC-005")
                rules = sorted({sf.code for sf in structural if sf.code.endswith(suffixes) and set(f.claim_ids) & set(sf.claim_ids)})
                if rules:
                    f = f.model_copy(update={"message": f.message + f" (branch rules: {', '.join(rules)})"})
            out.append(f)
        return out

    @_observed
    def respond(self, request_message_id: str, report: SpecialistReport, *, sender_agent_id: Optional[str] = None) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        """Check a specialist's report against the request it answers and deliver it with a receipt.

        ``sender_agent_id`` is the agent the hub says sent the report (raw text arriving
        through ``respond_text``); it defaults to the report's own ``agent_id``. The envelope
        is bound to that sender, so a report that claims another author is INT-ENV-008.
        Identity and integrity errors REJECT the transmission before any content check runs
        (nothing is pooled or stored); content findings travel with the delivered report."""
        # A request message id that is not a string of 1 to 128 characters names no request: the reply is REJECTED with
        # INT-REQ-000 like a reply to an unknown id, never an exception.
        request_message_id, id_problem = _message_id_given(request_message_id)
        req = self.requests.get(request_message_id) if request_message_id is not None else None
        findings: list[IntegrityFinding] = []
        try:
            sender = sender_agent_id or report.agent_id
            payload = report.model_dump(mode="json", exclude_none=True)
            msg = AgentMessage(message_id=uuid.uuid4().hex, request_id=report.request_id, task_id=report.task_id, sender_agent_id=sender,
                               sender_role=AgentRole.SPECIALIST, recipient_role=AgentRole.ROUTER, contract="specialist_report/1.0",
                               payload=payload, payload_sha256=payload_hash(payload), in_reply_to=request_message_id, created_at=_now())
        except Exception as exc:  # a report built around validation whose identity cannot head an envelope: refused, never raised (integration gate 3)
            agent = (sender_agent_id if isinstance(sender_agent_id, str) else None) or _text_attr(report, "agent_id") or ""
            return self._withheld_payload(request_message_id, report, agent_id=_scrub(agent)[:128], report_id=_text_attr(report, "report_id") or "", branch_key=self.branch.key,
                                          message=f"response from {_scrub(agent)[:128]!r} carrying a {type(report).__name__} cannot be put in an envelope ({type(exc).__name__}): "
                                                  "the report, built around its contract's validation, has no valid sender, request or task; it was not delivered")
        # The payload as delivered is re-validated before the envelope binding reads it, and every check reads the report
        # read back from it (integration gates 2 and 3), never the caller's object.
        image_findings = self._revalidate(report, payload)
        blocked = any(f.code in ("INT-REQ-009", "INT-HANDOFF-012") for f in image_findings)  # does not re-validate, or carries another report's claims
        if not blocked:
            report = self._as_delivered(report, payload)
            # rule bidi-text: the specialist's own text, as the recipient reads it, holds no bidirectional embedding, override or isolate
            # (a structured payload, or a report handed over as an object; raw text is refused before it is parsed, in respond_text)
            image_findings += report_bidi_findings(report)
            blocked = any(f.code == "INT-REQ-009" for f in image_findings)
        findings += self.log.accept(msg)
        if not blocked:
            findings += bind_payload(msg, report)
        findings += self._dedupe(msg)
        findings += image_findings
        bk = self._branch_for(sender)[0].key
        if req is None:
            findings.append(IntegrityFinding(code="INT-REQ-000", severity="error", message="response does not reply to any accepted request on this channel" + (f" ({id_problem})" if id_problem else ""),
                                             message_ids=[msg.message_id] + ([request_message_id] if request_message_id is not None else [])))
            return self._finish(msg, "specialist_to_router", findings, [], [], [], branch_key=bk)
        if blocked:
            return self._finish(msg, "specialist_to_router", findings, [], [], [], branch_key=bk)
        if sender != req.to_agent_id:
            findings.append(IntegrityFinding(code="INT-REQ-001", severity="error", message=f"response came from {sender} but the request was addressed to {req.to_agent_id}", agent_ids=sorted({sender, req.to_agent_id}), message_ids=[msg.message_id]))
        findings += check_report_against_plan(self.plan, report)
        findings += self._report_id_reuse(report, msg, findings)
        # Quotations are checked against the texts the router sent, never against texts the specialist supplies: a report
        # text that is not byte-identical to a request text under its document id (a document the router never sent, or a
        # sent one replaced) is INT-REQ-002, whether or not the request carried texts.
        supplied = list(req.supplied_texts)
        findings += self._supplied_text_mismatch(report, req)
        if _is_blocking(findings):  # identity or integrity violation: nothing of this report is checked for content, pooled or stored
            return self._finish(msg, "specialist_to_router", findings, [], [], [], branch_key=bk)
        # Every content check runs guarded: one that fails internally is INT-INTERNAL-001 naming it, the rest of the receipt is
        # kept and the report is still delivered (nothing raises into the router).
        rid = dict(report_ids=[report.report_id], agent_ids=[report.agent_id])
        findings += self._guarded("claim-id collision", findings, lambda: self._claim_id_collisions(report), [], **rid)
        covered, form_covered, source_findings = self._guarded("source integrity (quotations against the supplied texts)", findings, lambda: self._source_findings(report, supplied, request_text=req.user_input), (set(), set(), []), **rid)
        findings += source_findings
        uncredited = self._guarded("uncredited quotations (INT-REQ-003)", findings, lambda: self._uncredited_quotations(report, supplied, request_text=req.user_input), [], **rid)
        findings += uncredited
        findings += self._guarded("peer figures (INT-REQ-014)", findings, lambda: self._peer_figures(report, supplied), [], **rid)
        findings += self._guarded("relayed check results (INT-REQ-014)", findings, lambda: self._relayed_check_results(report, supplied), [], **rid)
        findings += self._guarded("folded claims (INT-REQ-013)", findings, lambda: self._fold_findings(report, supplied), [], **rid)
        branch, profile = self._branch_for(report.agent_id)
        hooks = branch.hub_hooks  # the branch's readings for the hub (the STEM branches only); each refines a heuristic and never raises
        exempt = bool(hooks) and self._hook(lambda: hooks.echo_exempt(report.original_response, req.user_input, profile.key), False)
        echo = None if exempt else self._guarded("request echo (INT-REQ-011)", findings, lambda: self._request_echo(req, report, supplied), None, **rid)
        if echo is not None:
            findings.append(echo)
        view = (lambda t: self._hook(lambda: hooks.word_count_view(t, profile.key), t)) if hooks else None
        findings += self._guarded("answer presence (INT-REQ-012)", findings, lambda: self._no_answer(report, view=view), [], **rid)
        withheld = self._guarded("a declined or deferred deliverable (INT-REQ-004)", findings, lambda: withheld_deliverable(report.original_response), None, **rid)
        coverage = self._guarded("request coverage (INT-REQ-004)", findings, lambda: self._coverage(req, report, echoed=echo is not None, hooks=hooks, profile_key=profile.key), [], **rid)
        for cov in coverage:
            if not cov.addressed:
                item = next(i for i in req.items if i.item_id == cov.item_id)
                why = ""
                if withheld is not None:
                    why = (f"; the answer declines the deliverable ({withheld[1][:200]!r}): the item is declined, not answered" if withheld[0] == "declined"
                           else f"; the answer defers the deliverable to the student's reply ({withheld[1][:200]!r}): the item is pending, not answered")
                findings.append(IntegrityFinding(code="INT-REQ-004", severity="warning" if item.required else "info", message=f"request item {cov.item_id} appears unaddressed: {item.text[:120]!r} (heuristic)" + why + (f"; {cov.note}" if getattr(cov, "note", None) else ""), claim_ids=[]))
        # Command terms C6: evaluate / discuss / to what extent / assess / examine / justify / recommend / give a judgement
        # need a judgement or position on degree. A judgement-role claim counts; so does a point, thesis, link or analysis
        # claim that states a position (verdict cue); a bare claim does not. A claim roled 'other' (a note, a self-report) never counts.
        verdict_present = any(c.claim_role == "judgement" or (c.claim_role in _VERDICT_ROLES and _VERDICT_CUE.search(c.claim_text)) for c in report.claims)
        for item in req.items:
            if item.level == 3 and item.command_term in LEVEL3_VERDICT_TERMS and not verdict_present:
                findings.append(IntegrityFinding(code="INT-REQ-008", severity="warning", message=f"item {item.item_id} uses the command term {item.command_term!r}, which requires a judgement or position on degree; no judgement/point claim was found (command terms C6)", claim_ids=[]))
        constraint_results, formal_ids = self._guarded("request constraints (INT-REQ-005)", findings, lambda: self._constraints(req, report, view=view), ([], []), **rid)
        structural, branch_formal, branch_ids = self._branch_checks(report, req, findings, frozenset(covered), frozenset(form_covered))
        # a quotation refuted against the supplied texts is not also "unverifiable"; with no text supplied, a quotation the
        # request alone refutes keeps the pack's CORE-SRC-003 beside the error (no supplied text holds it either)
        refuted = {cid for f in uncredited if supplied for cid in f.claim_ids}
        if refuted:  # the same quotation is not also "unverifiable": the hub found it in none of the supplied texts
            structural = [sf for sf in structural if not (sf.code == "CORE-SRC-003" and sf.claim_ids and set(sf.claim_ids) <= refuted)]
        findings = self._name_branch_rules(findings, structural)
        findings += self._guarded("credits to texts not supplied (INT-REQ-015)", findings, lambda: self._foreign_credits(report, supplied, structural), [], **rid)
        formal_ids = list(formal_ids) + branch_ids
        by_cid = {c.constraint_id: c for c in req.constraints}
        for cr in constraint_results:
            if cr.satisfied is False:
                # A paragraph bound is measured over blank-line blocks; a specialist may set one paragraph out as several blocks
                # (point, strands, link), so an overrun is a layout warning for the router, not an error like a word limit. An
                # "about N words" band is a target, so a measure outside it but within a quarter of N is a warning too (round-8
                # clearance c1; ``request_parser.word_bound_severity``, which the transfer auditor's rule reads on its recount).
                bound = by_cid.get(cr.constraint_id)
                layout = bound is not None and bound.kind.endswith("paragraphs")
                findings.append(IntegrityFinding(code="INT-REQ-005", severity=word_bound_severity(bound, measured_of(cr.detail)),
                                                 message=f"constraint {cr.constraint_id} not satisfied: {cr.detail}" + (" (blank-line blocks; a paragraph set out in blocks counts as several)" if layout else ""),
                                                 formal_result_id=cr.formal_result_id, deterministic=cr.method != "formal"))
        self._guarded("supersession (INT-HANDOFF-009)", findings, lambda: self._supersession(report, findings), None, **rid)
        # An echo of the request answers nothing: its outcomes are delivered for the record but never pooled, so its
        # formalizations cannot displace the agent's genuine claims under the same ids.
        outcomes = self._guarded("claim verification", findings, lambda: self._verify_claims(report, findings, pool=echo is None, task=self._task_record(req)), [], **rid)
        report_named = self._guarded("argument diagnosis (report level)", findings, lambda: self._report_diagnosis(report, req, outcomes), None, **rid)
        if not _is_blocking(findings):  # delivered <=> transmitted: a synthesis may cite any report the router received
            self.transmitted_reports.setdefault(report.report_id, report)
            self.report_deliveries.setdefault(report.report_id, set()).add(msg.message_id)
        return self._finish(msg, "specialist_to_router", findings, coverage, constraint_results, outcomes, formal_ids, structural=structural, branch_formal=branch_formal, branch_key=bk,
                            report=report, report_named=report_named)

    # --------------------------------------------------------------- agent relay
    @_observed
    def relay(self, from_agent_id: str, from_role: AgentRole, to_agent_id: str, to_role: AgentRole,
              payload_obj: Union[SpecialistReport, Synthesis], in_reply_to: Optional[str] = None) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        """Carry a report or a synthesis between agents. A payload handed over as a mapping (JSON as received) is validated
        against the contract its shape names (``synthesis_id``: synthesis/1.0, ``report_id``: specialist_report/1.0) first;
        anything else, or a mapping that does not validate, is REJECTED with INT-REQ-009 and nothing raises. A synthesis
        that fails on a value outside one of the contract's closed vocabularies (a transformation written as free text,
        say) is also named with INT-SYNTH-014; a synthesis object built around validation is re-validated and refused the
        same way (``_revalidate_synthesis``)."""
        # a role given as its value ("router") is that role, as the envelope reads it; anything else is left as given
        from_role, to_role = _as_role(from_role), _as_role(to_role)
        if not isinstance(payload_obj, (SpecialistReport, Synthesis)):
            provenance = _raw_claim_provenance(payload_obj) if isinstance(payload_obj, Mapping) and "report_id" in payload_obj and "synthesis_id" not in payload_obj else []
            if provenance:  # decided on the payload as received, before contract validation (never a bare value error)
                return self._withheld_payload(in_reply_to, payload_obj, agent_id=_scrub(str(from_agent_id))[:128], report_id=_scrub(str(payload_obj.get("report_id") or ""))[:128], branch_key=self.branch.key,
                                              message="", sender_role=from_role if isinstance(from_role, AgentRole) else AgentRole.SPECIALIST,
                                              recipient_role=to_role if isinstance(to_role, AgentRole) else AgentRole.ROUTER, recipient_agent_id=(_scrub(str(to_agent_id))[:128] or None), findings=provenance)
            coerced, why, named = _coerce_payload(payload_obj)
            if coerced is None:
                rid = str(payload_obj.get("report_id") or payload_obj.get("synthesis_id") or "") if isinstance(payload_obj, Mapping) else ""
                return self._withheld_payload(in_reply_to, payload_obj, agent_id=_scrub(str(from_agent_id))[:128], report_id=_scrub(rid)[:128], branch_key=self.branch.key,
                                              message=f"relay from {from_agent_id!r} to {to_agent_id!r} carries {why}; it was not delivered",
                                              sender_role=from_role if isinstance(from_role, AgentRole) else AgentRole.SPECIALIST,
                                              recipient_role=to_role if isinstance(to_role, AgentRole) else AgentRole.ROUTER, recipient_agent_id=(_scrub(str(to_agent_id))[:128] or None),
                                              named=named)
            payload_obj = coerced
        findings: list[IntegrityFinding] = []
        forward = isinstance(payload_obj, SpecialistReport) and from_role is AgentRole.ROUTER
        contract = ("specialist_report_forward/1.0" if forward else "specialist_report/1.0") if isinstance(payload_obj, SpecialistReport) else "synthesis/1.0"
        try:
            payload = payload_obj.model_dump(mode="json", exclude_none=True)
            msg = AgentMessage(message_id=uuid.uuid4().hex, request_id=payload_obj.request_id, task_id=payload_obj.task_id, sender_agent_id=from_agent_id,
                               sender_role=from_role, recipient_role=to_role, recipient_agent_id=to_agent_id, contract=contract,
                               payload=payload, payload_sha256=payload_hash(payload), in_reply_to=in_reply_to, created_at=_now())
        except Exception as exc:  # a payload built around validation, or relay fields, that cannot be put in an envelope: refused, never raised
            rid = str(getattr(payload_obj, "report_id", None) or getattr(payload_obj, "synthesis_id", None) or "")
            return self._withheld_payload(in_reply_to, payload_obj, agent_id=_scrub(str(from_agent_id))[:128], report_id=_scrub(rid)[:128], branch_key=self.branch.key,
                                          message=f"relay from {_scrub(str(from_agent_id))[:128]!r} to {_scrub(str(to_agent_id))[:128]!r} carrying a {type(payload_obj).__name__} "
                                                  f"cannot be put in an envelope ({type(exc).__name__}): the payload, built around its contract's validation, or the "
                                                  "relay's own fields (sender, recipient, roles) do not validate; it was not delivered",
                                          sender_role=from_role if isinstance(from_role, AgentRole) else AgentRole.SPECIALIST,
                                          recipient_role=to_role if isinstance(to_role, AgentRole) else AgentRole.ROUTER, recipient_agent_id=(_scrub(str(to_agent_id))[:128] or None))
        # The payload as delivered is re-validated FIRST, and every identity, party and content check below reads the
        # object read back from it (integration gate 3): the envelope binding, the party checks and the id-reuse checks ran
        # on the caller's object before, so an object built around validation (``model_construct``, ``model_copy(update=...)``,
        # a subclass whose dump differs from its attributes) raised out of the relay (a field missing, None or unhashable)
        # or was delivered under an identity no check saw (a combinator the plan did not select). A payload that does not
        # re-validate is REJECTED with INT-REQ-009 after the envelope-level checks only (they read the envelope, never the
        # object), as a mapping that does not validate is.
        bk = self._branch_for(_text_attr(payload_obj, "agent_id"))[0].key if isinstance(payload_obj, SpecialistReport) else self.branch.key
        if isinstance(payload_obj, Synthesis):
            image_findings, image = self._revalidate_synthesis(payload_obj, payload)
        else:
            image_findings = self._revalidate(payload_obj, payload)
            image = None if any(f.code in ("INT-REQ-009", "INT-HANDOFF-012") for f in image_findings) else self._as_delivered(payload_obj, payload)
        if image is None:
            refused = self.log.accept(msg) + self._dedupe(msg) + self._relay_parties(msg, from_role, to_agent_id, to_role, None) + image_findings
            return self._finish(msg, "agent_to_agent", refused, [], [], [], branch_key=bk)
        payload_obj = image  # every check reads the payload as delivered (integration gates 2 and 3), never the caller's object
        findings += self.log.accept(msg)
        if not forward:  # a forward carries another agent's report by design; every other relay must come from the payload's owner
            findings += bind_payload(msg, payload_obj)
        findings += self._dedupe(msg)
        findings += self._relay_parties(msg, from_role, to_agent_id, to_role, payload_obj)
        findings += image_findings
        if payload_obj.request_id != self.plan.request_id or payload_obj.task_id != self.plan.task_id:
            findings.append(IntegrityFinding(code="INT-HANDOFF-001", severity="error", message="relayed payload belongs to another request/task", message_ids=[msg.message_id]))
        outcomes: list[ClaimVerificationOutcome] = []
        structural: list[StructuralFinding] = []
        branch_formal: list[ConstraintResult] = []
        branch_ids: list[str] = []
        relayed_report: Optional[SpecialistReport] = None  # a relayed report checked for content: its report-level argument diagnosis
        relayed_named = None
        if isinstance(payload_obj, SpecialistReport):
            bk = self._branch_for(payload_obj.agent_id)[0].key
            if forward:
                # The router may only pass on a report exactly as it was delivered on this channel: same report id,
                # same payload digest. Anything else is a report altered in transit or never received.
                held = self.transmitted_reports.get(payload_obj.report_id)
                if held is None:
                    findings.append(IntegrityFinding(code="INT-HANDOFF-013", severity="error", message=f"router forwarded report {payload_obj.report_id!r}, which was never delivered on this channel", report_ids=[payload_obj.report_id], agent_ids=[from_agent_id, to_agent_id], message_ids=[msg.message_id]))
                elif payload_hash(held.model_dump(mode="json", exclude_none=True)) != msg.payload_sha256:
                    findings.append(IntegrityFinding(code="INT-HANDOFF-013", severity="error", message=f"router forwarded report {payload_obj.report_id!r} with a payload that differs from the one delivered on this channel (altered in transit)", report_ids=[payload_obj.report_id], agent_ids=[from_agent_id, to_agent_id], message_ids=[msg.message_id]))
                elif (msg.in_reply_to is not None and msg.in_reply_to not in self.report_deliveries.get(payload_obj.report_id, ())
                      and not any(f.code == "INT-ENV-003" for f in findings)):
                    # a forward replies to the delivery of the report it carries: one replying to another message (another
                    # report's delivery, a request) is not tied to that delivery (router-envelope-5; an unknown id is INT-ENV-003)
                    delivered = sorted(self.report_deliveries.get(payload_obj.report_id, ()))
                    findings.append(IntegrityFinding(code="INT-HANDOFF-013", severity="error",
                                                     message=f"router forwarded report {payload_obj.report_id!r} in reply to message {msg.in_reply_to!r}, which is not a delivery of that report on this channel "
                                                             f"(delivered as {', '.join(repr(m) for m in delivered) or 'no message'}); a forward must reply to the delivery of the report it carries",
                                                     report_ids=[payload_obj.report_id], agent_ids=[from_agent_id, to_agent_id], message_ids=[msg.message_id, msg.in_reply_to] + delivered))
                if _is_blocking(findings):
                    return self._finish(msg, "agent_to_agent", findings, [], [], [], branch_key=bk)
                # The delivered report was already parsed, checked and pooled on arrival; a faithful forward re-runs
                # the hand-off checks (plan scope, self-reports) but not the subject packs and verification.
                findings += check_report_against_plan(self.plan, payload_obj)
                if payload_obj.report_id in self.superseded:
                    findings.append(IntegrityFinding(code="INT-HANDOFF-014", severity="warning", message=f"router forwarded report {payload_obj.report_id!r}, which agent {payload_obj.agent_id!r} superseded with report {self.superseded[payload_obj.report_id]!r} on this channel; the recipient receives a superseded report", report_ids=[payload_obj.report_id, self.superseded[payload_obj.report_id]], agent_ids=[payload_obj.agent_id, to_agent_id], message_ids=[msg.message_id]))
                self.forwards.setdefault(payload_obj.report_id, []).append((to_agent_id, msg.message_id))
                return self._finish(msg, "agent_to_agent", findings, [], [], [], branch_key=bk)
            # A specialist's relay of a report is a hand-off of a report already delivered to the router on this channel in
            # reply to a request: a new report enters only through respond(). A report never delivered is refused
            # (INT-HANDOFF-013); one delivered under its id by another agent or with other content is INT-ENV-008 /
            # INT-HANDOFF-015 (below). A relay never changes the channel's state: it stores, pools and supersedes nothing.
            if payload_obj.report_id not in self.transmitted_reports:
                findings.append(IntegrityFinding(code="INT-HANDOFF-013", severity="error", message=f"agent {from_agent_id!r} relayed report {payload_obj.report_id!r}, which was never delivered to the router on this channel in reply to a request; "
                                                 "a report reaches other agents only after its delivery, so it was not delivered", report_ids=[payload_obj.report_id], agent_ids=sorted({from_agent_id, to_agent_id}), message_ids=[msg.message_id]))
            findings += check_report_against_plan(self.plan, payload_obj)
            findings += self._report_id_reuse(payload_obj, msg, findings)
            if _is_blocking(findings):  # identity or integrity violation: nothing of this report is checked for content, pooled or stored
                return self._finish(msg, "agent_to_agent", findings, [], [], [], branch_key=bk)
            rid = dict(report_ids=[payload_obj.report_id], agent_ids=[payload_obj.agent_id])
            findings += self._guarded("claim-id collision", findings, lambda: self._claim_id_collisions(payload_obj), [], **rid)
            findings += self._guarded("folded claims (INT-REQ-013)", findings, lambda: self._fold_findings(payload_obj, payload_obj.supplied_texts), [], **rid)
            structural, branch_formal, branch_ids = self._branch_checks(payload_obj, None, findings)
            findings += self._guarded("credits to texts not supplied (INT-REQ-015)", findings, lambda: self._foreign_credits(payload_obj, payload_obj.supplied_texts, structural), [], **rid)
            if payload_obj.report_id in self.superseded:
                findings.append(IntegrityFinding(code="INT-HANDOFF-014", severity="warning", message=f"agent {from_agent_id!r} relayed report {payload_obj.report_id!r}, which agent {payload_obj.agent_id!r} superseded with report {self.superseded[payload_obj.report_id]!r} on this channel; the recipient receives a superseded report", report_ids=[payload_obj.report_id, self.superseded[payload_obj.report_id]], agent_ids=sorted({from_agent_id, to_agent_id}), message_ids=[msg.message_id]))
            # the delivered report's formalizations were pooled on its delivery: verified again for this receipt, never re-pooled
            outcomes = self._guarded("claim verification", findings, lambda: self._verify_claims(payload_obj, findings, pool=False), [], **rid)
            relayed_report, relayed_named = payload_obj, self._guarded("argument diagnosis (report level)", findings,
                                                                       lambda: self._report_diagnosis(payload_obj, None, outcomes), None, **rid)
        else:
            findings += self._synthesis_id_reuse(payload_obj, msg, findings)
            if _is_blocking(findings):  # an invalid synthesis, an unselected or impersonating combinator, or a reused synthesis id: its ledger is not examined
                return self._finish(msg, "agent_to_agent", findings, [], [], [], branch_key=bk)
            sid = dict(claim_ids=[payload_obj.synthesis_id], agent_ids=[payload_obj.combinator_agent_id])
            scope = self._guarded("ledger scope", findings, lambda: self._ledger_scope(payload_obj), [], **sid)
            findings += self._guarded("superseded citations (INT-HANDOFF-014)", findings, lambda: self._cited_superseded(payload_obj), [], **sid)
            findings += self._guarded("claim ledger (INT-LEDGER)", findings, lambda: self._explain_superseded_collisions(check_synthesis_ledger(scope, payload_obj, extra_texts=self._request_texts(), document_texts=self._request_documents(), allowed_document_ids=self.plan.allowed_document_ids)), [], **sid)
            conflict_findings, conflict_ids = self._guarded("conflict disclosure (INT-CONFLICT-002)", findings, lambda: self._synthesis_conflicts(payload_obj, scope), ([], []), **sid)
            findings += conflict_findings
            branch_ids += conflict_ids
            ent_findings, ent_ids, checked = self._guarded("synthesis entailment (INT-SYNTH)", findings, lambda: self._synthesis_entailment(payload_obj), ([], [], {}), **sid)
            findings += ent_findings
            branch_ids += ent_ids
            findings = self._state_synthesis_checks(findings, checked)
            findings += self._guarded("unchecked paraphrases (INT-SYNTH-012)", findings, lambda: self._unchecked_paraphrases(payload_obj, scope, checked), [], **sid)
            if not _is_blocking(findings):
                self.syntheses.setdefault(payload_obj.synthesis_id, payload_obj)
        return self._finish(msg, "agent_to_agent", findings, [], [], outcomes, branch_ids, structural=structural, branch_formal=branch_formal, branch_key=bk,
                            report=relayed_report, report_named=relayed_named)

    def _revalidate_synthesis(self, synthesis: Synthesis, payload: dict) -> tuple[list[IntegrityFinding], Optional[Synthesis]]:
        """The synthesis delivered to the recipient must re-validate against synthesis/1.0, as a report must against its
        contract (``_revalidate``): a synthesis built around validation (``model_copy(update=...)`` or ``model_construct``,
        with a transformation written as free text, say) is REJECTED here with INT-REQ-009, and a value outside one of
        the contract's closed vocabularies is named (INT-SYNTH-014), instead of reaching the claim ledger, whose rules
        those values select. A synthesis that validated on construction re-validates unchanged, so this adds nothing to
        its receipt.

        Both forms are validated (integration gate 2): the object's full dump, None kept, so a None in a field that has a
        default but is not Optional (``transformation``, ``certainty``, ``ledger``, ...) is refused and named instead of
        being dropped from the delivered payload and read back as the default; and the delivered payload itself. Returns
        the findings and, when both validate, the synthesis the recipient reads from the delivered payload: every check of
        the relay runs on it, never on the caller's object, so the ledger examines exactly what is delivered and hashed."""
        sid, cid = _scrub(str(getattr(synthesis, "synthesis_id", "") or ""))[:128], _scrub(str(getattr(synthesis, "combinator_agent_id", "") or ""))[:128]
        for data in (_full_dump(synthesis), payload):
            if data is None:
                return [IntegrityFinding(code="INT-REQ-009", severity="error",
                                         message="synthesis payload cannot be dumped in full for re-validation and is not delivered: a synthesis built around its "
                                                 "contract's validation",
                                         claim_ids=[sid] if sid else [], agent_ids=[cid] if cid else [])], None
            try:
                image = Synthesis.model_validate(data)
            except (ValidationError, TypeError, ValueError) as exc:
                out = [IntegrityFinding(code="INT-REQ-009", severity="error",
                                        message=f"synthesis payload does not re-validate against the synthesis contract and is not delivered: {_shape_reason(exc, 'synthesis')}",
                                        claim_ids=[sid] if sid else [], agent_ids=[cid] if cid else [])]
                return out + (_vocabulary_findings(data, exc) if isinstance(exc, ValidationError) else []), None
        return [], image

    def _synthesis_id_reuse(self, synthesis: Synthesis, msg: AgentMessage, findings: list[IntegrityFinding]) -> list[IntegrityFinding]:
        """A synthesis id already delivered on this channel: the same content (``created_at`` aside) again to a recipient
        that already received it is a duplicate delivery (INT-ENV-001); different content is INT-HANDOFF-015 naming the
        fields that differ, and is not delivered. The first delivery is kept; ``syntheses`` is never overwritten."""
        held = self.syntheses.get(synthesis.synthesis_id)
        if held is None:
            return []
        ids = dict(claim_ids=[synthesis.synthesis_id], agent_ids=sorted({held.combinator_agent_id, msg.sender_agent_id}), message_ids=[msg.message_id])
        old = held.model_dump(mode="json", exclude_none=True, exclude={"created_at"})
        new = synthesis.model_dump(mode="json", exclude_none=True, exclude={"created_at"})
        if old == new:
            if any(f.code == "INT-ENV-001" for f in findings) or self._recipient_key(msg) not in self.synthesis_recipients.get(synthesis.synthesis_id, set()):
                return []
            return [IntegrityFinding(code="INT-ENV-001", severity="warning", message=f"synthesis {synthesis.synthesis_id!r} was already delivered to this recipient on this channel (identical content; only the timestamp differs): a duplicate delivery; the first delivery is kept", **ids)]
        changed = sorted(k for k in old.keys() | new.keys() if old.get(k) != new.get(k))
        changed_claims = sorted({c.get("claim_id") for c in old.get("claims", [])} ^ {c.get("claim_id") for c in new.get("claims", [])}
                                | {c.get("claim_id") for c in new.get("claims", []) if c not in old.get("claims", [])})
        detail = f"; synthesized claims added, removed or changed: {changed_claims[:8]}" if changed_claims else ""
        return [IntegrityFinding(code="INT-HANDOFF-015", severity="error", message=f"synthesis id {synthesis.synthesis_id!r} reused with DIFFERENT content ({changed} differ{detail}): a synthesis of combinator {held.combinator_agent_id!r} was already delivered under this id; the first delivery is kept and this transmission is not delivered (a revised synthesis needs a new synthesis id)", **ids)]

    def _relay_parties(self, msg: AgentMessage, from_role: AgentRole, to_agent_id: str, to_role: AgentRole, payload_obj: BaseModel) -> list[IntegrityFinding]:
        """Sender and recipient of a relay must be parties the plan selected, unless they act in an
        infrastructure role (the router, the Overseer); a synthesis must name a selected combinator."""
        out: list[IntegrityFinding] = []
        selected = set(self.plan.selected_agent_ids)
        ids = dict(message_ids=[msg.message_id])
        # An infrastructure role is held, not asserted: a party the plan selects as a specialist or combinator never acts
        # as the router or the Overseer, and the router of this channel is the agent that sent its requests.
        if from_role in _INFRASTRUCTURE_ROLES and msg.sender_agent_id in selected:
            out.append(IntegrityFinding(code="INT-ENV-007", severity="error", message=f"relay sender {msg.sender_agent_id!r} asserts the {from_role.value} role, but the plan selects it as a specialist or combinator: role impersonation; not delivered", agent_ids=[msg.sender_agent_id], **ids))
        elif from_role is AgentRole.ROUTER and self.router_ids and msg.sender_agent_id not in self.router_ids:
            out.append(IntegrityFinding(code="INT-ENV-007", severity="error", message=f"relay sender {msg.sender_agent_id!r} asserts the router role, but the router of this channel is {sorted(self.router_ids)} (the sender of its requests): role impersonation; not delivered", agent_ids=[msg.sender_agent_id], **ids))
        if to_role in _INFRASTRUCTURE_ROLES and to_agent_id in selected:
            out.append(IntegrityFinding(code="INT-ENV-007", severity="error", message=f"relay addressed to {to_agent_id!r} in the {to_role.value} role, but the plan selects it as a specialist or combinator; it does not hold that role; not delivered", agent_ids=[to_agent_id], **ids))
        if from_role not in _INFRASTRUCTURE_ROLES and msg.sender_agent_id not in selected:
            out.append(IntegrityFinding(code="INT-HANDOFF-002", severity="error", message=f"relay sent by {from_role.value} {msg.sender_agent_id!r}, which the plan did not select (selected: {sorted(selected)})", agent_ids=[msg.sender_agent_id], **ids))
        if to_role not in _INFRASTRUCTURE_ROLES and to_agent_id not in selected:
            out.append(IntegrityFinding(code="INT-HANDOFF-002", severity="error", message=f"relay addressed to {to_role.value} {to_agent_id!r}, which the plan did not select (selected: {sorted(selected)})", agent_ids=[to_agent_id], **ids))
        if isinstance(payload_obj, Synthesis) and payload_obj.combinator_agent_id not in selected:  # None: a payload refused before its identity is read
            out.append(IntegrityFinding(code="INT-HANDOFF-002", severity="error", message=f"synthesis {payload_obj.synthesis_id!r} names combinator {payload_obj.combinator_agent_id!r}, which the plan did not select (selected: {sorted(selected)})", agent_ids=[payload_obj.combinator_agent_id], claim_ids=[payload_obj.synthesis_id], **ids))
        return out

    def _ledger_scope(self, synthesis: Synthesis) -> list[SpecialistReport]:
        """Reports a synthesis must account for: every report it cites plus each agent's
        CURRENT report (the last one delivered). An earlier report the same agent
        superseded (INT-HANDOFF-009) is out of scope unless the synthesis cites it, in
        which case mixing it with the current one is reported by the ledger (INT-LEDGER-014)."""
        latest: dict[str, str] = {}
        for r in self.transmitted_reports.values():  # delivery order
            latest[r.agent_id] = r.report_id
        cited = set(synthesis.source_report_ids)
        return [r for r in self.transmitted_reports.values() if r.report_id in cited or latest.get(r.agent_id) == r.report_id]

    def _cited_superseded(self, synthesis: Synthesis) -> list[IntegrityFinding]:
        """A synthesis citing a report its agent superseded on this channel is told so (INT-HANDOFF-014)."""
        out: list[IntegrityFinding] = []
        for rid in synthesis.source_report_ids:
            newer = self.superseded.get(rid)
            if newer is None:
                continue
            agent = self.transmitted_reports[rid].agent_id if rid in self.transmitted_reports else "?"
            out.append(IntegrityFinding(code="INT-HANDOFF-014", severity="warning", message=f"synthesis cites report {rid!r}, which agent {agent!r} superseded with report {newer!r} on this channel (INT-HANDOFF-009); the synthesis should account for the current report", report_ids=[rid, newer], agent_ids=[agent, synthesis.combinator_agent_id], claim_ids=[synthesis.synthesis_id]))
        return out

    def _explain_superseded_collisions(self, findings: list[IntegrityFinding]) -> list[IntegrityFinding]:
        """An id collision between a superseded report and its successor is a supersession, and is said to be one."""
        out: list[IntegrityFinding] = []
        for f in findings:
            if f.code == "INT-LEDGER-014" and f.report_ids:
                pairs = [(old, new) for old, new in self.superseded.items() if old in f.report_ids and new in f.report_ids]
                if pairs and len(set(f.report_ids)) == len({x for p in pairs for x in p}):
                    note = "; ".join(f"report {old!r} was superseded by {new!r} on this channel" for old, new in pairs)
                    f = f.model_copy(update={"message": f"{f.message} ({note}: the synthesis cites a superseded report alongside the current one, not two independent reports)"})
            out.append(f)
        return out

    def _synthesis_conflicts(self, synthesis: Synthesis, scope: list[SpecialistReport]) -> tuple[list[IntegrityFinding], list[str]]:
        """Joint consistency of the formalized claims the synthesis must account for, and the
        disclosure of every contradiction among them (INT-CONFLICT-002): the same rule
        ``run_integrity_checks`` applies, run on the channel when the synthesis arrives."""
        scope_ids = {c.claim_id for r in scope for c in r.claims}
        pool = [p for cid, p in self.formalized.items() if cid in scope_ids]
        out: list[IntegrityFinding] = []
        ids: list[str] = []
        sets: list[tuple[frozenset[str], Optional[str]]] = []
        if len(pool) >= 2:
            res, f = check_cross_report_consistency(pool, request_id=self.plan.request_id, config=self.config, signing_key=self.key, assumed_readings=frozenset(self.ambiguous_pooled))
            if res is not None:
                ids.append(res.result_id)
            f = self._with_report_ids(f)
            out += f
            sets += [(frozenset(x.claim_ids), x.formal_result_id) for x in f if x.code == "INT-CONFLICT-001"]
        # contradictions named earlier on this channel among the claims in scope (their formalizations may since have left the pool)
        sets += [(claims, rid) for claims, rid in self.conflicts_seen if claims <= scope_ids]
        out += self._with_report_ids(check_conflict_disclosure(synthesis, sets))
        out += self._with_report_ids(check_conflict_records(synthesis, sets))  # INT-CONFLICT-006: a record over claims the hub found no contradiction between
        return out, ids

    def _synthesis_entailment(self, synthesis: Synthesis) -> tuple[list[IntegrityFinding], list[str], dict[str, Optional[str]]]:
        """For each synthesized claim with formalized sources: obtain a formal conclusion
        (the combinator's ``formal_conclusion`` or the channel's hook) and decide, with
        the engine, whether it follows from the sources it cites. Returns the findings,
        the signed result ids, and per claim the result id of the check or None when
        none could be run."""
        out: list[IntegrityFinding] = []
        ids: list[str] = []
        checked: dict[str, Optional[str]] = {}
        for sc in synthesis.claims:
            sources = [self.formalized[s] for s in sc.source_claim_ids if s in self.formalized]
            if not sources:
                continue
            unformalized = [s for s in sc.source_claim_ids if s not in self.formalized]
            concl = sc.formal_conclusion
            if concl is None and self.formalize_synthesis_fn is not None:
                try:
                    concl = self.formalize_synthesis_fn(sc, sources)
                except Exception as exc:  # the channel never drops a message because a hook crashed
                    out.append(IntegrityFinding(code="INT-SYNTH-013", severity="warning", message=f"formalization of synthesized claim {sc.claim_id} failed internally ({type(exc).__name__}); its entailment was not checked", claim_ids=[sc.claim_id]))
            if concl is None:
                checked[sc.claim_id] = None
                continue
            res, f = check_synthesis_entailment(sources, concl, request_id=self.plan.request_id, synthesized_claim_id=sc.claim_id, config=self.config, signing_key=self.key, unformalized_source_ids=unformalized)
            out += self._with_report_ids(f)
            if res is not None:
                ids.append(res.result_id)
                ids.extend(rid for x in f for rid in x.related_result_ids)
            checked[sc.claim_id] = res.result_id if res is not None else None
            if sc.transformation in ("carried", "paraphrased") and len(sources) == 1 and not unformalized:
                res2, f2 = check_paraphrase_coverage(sources[0], concl, request_id=self.plan.request_id, synthesized_claim_id=sc.claim_id, config=self.config, signing_key=self.key)
                out += f2
                if res2 is not None:
                    ids.append(res2.result_id)
        return out, ids, checked

    def _request_documents(self) -> dict[str, str]:
        """The supplied texts the requests on this channel carried, by document id (the first text per id): the documents
        a synthesized claim's evidence reference may name besides the reports' own supplied texts."""
        out: dict[str, str] = {}
        for req in self.requests.values():
            for t in req.supplied_texts:
                out.setdefault(t.document_id, t.text)
        return out

    def _request_texts(self) -> list[str]:
        """Every text a request on this channel carried (user inputs and supplied texts): where a synthesized quotation
        may legitimately come from besides the reports."""
        out: list[str] = []
        for req in self.requests.values():
            out.append(req.user_input)
            out += [t.text for t in req.supplied_texts]
        return list(dict.fromkeys(out))

    @staticmethod
    def _unchecked_paraphrases(synthesis: Synthesis, scope: list[SpecialistReport], checked: dict[str, Optional[str]]) -> list[IntegrityFinding]:
        """INT-SYNTH-012 (warning) on the channel: a material 'paraphrased', 'narrowed', 'merged' or 'generalized' claim
        whose content change no formal conclusion checked here, so the router never reads an unchecked rewording or
        combination of material content as checked (``run_integrity_checks`` applies the same rule, with INT-SYNTH-006 for
        a merged or generalized claim; on the channel the content is delivered, so the finding is a warning)."""
        sources = {c.claim_id: c for r in scope for c in r.claims}
        out: list[IntegrityFinding] = []
        for sc in synthesis.claims:
            if sc.transformation not in ("paraphrased", "narrowed", "merged", "generalized") or checked.get(sc.claim_id):
                continue
            known = [sources[x] for x in sc.source_claim_ids if x in sources]
            if sc.materiality != "material" and not any(c.materiality == "material" for c in known):
                continue
            out.append(IntegrityFinding(code="INT-SYNTH-012", severity="warning", message=f"material claim produced by '{sc.transformation}' from {list(sc.source_claim_ids)}: its content change was NOT formally checked on this channel (no formal conclusion was supplied or could be formed), so the router must not treat the rewording as checked",
                                        claim_ids=[sc.claim_id] + list(sc.source_claim_ids), agent_ids=[synthesis.combinator_agent_id]))
        return out

    @staticmethod
    def _state_synthesis_checks(findings: list[IntegrityFinding], checked: dict[str, Optional[str]]) -> list[IntegrityFinding]:
        """The ledger's INT-LEDGER-011 says a formal check is required; the receipt must
        say whether this channel performed it."""
        out: list[IntegrityFinding] = []
        for f in findings:
            if f.code == "INT-LEDGER-011" and f.claim_ids:
                rid = checked.get(f.claim_ids[0])
                if rid:
                    f = f.model_copy(update={"message": f.message.replace("check required", f"check performed on this channel (formal result {rid})"), "formal_result_id": rid})
                else:
                    f = f.model_copy(update={"message": f.message.replace("check required", "check " + _NOT_PERFORMED)})
            out.append(f)
        return out

    # ------------------------------------------------------------------ internals
    @staticmethod
    def _guarded(name: str, findings: list[IntegrityFinding], fn: Callable[[], object], default, **ids):
        """``fn()``, or ``default`` when it fails internally: the failure is INT-INTERNAL-001 naming the check (its findings
        are missing from the receipt and must not be read as a pass), the other checks still reach the receipt and the
        transmission is still delivered. Nothing raises into the router."""
        try:
            return fn()
        except Exception as exc:  # a content check that fails never takes the transmission down
            findings.append(IntegrityFinding(code="INT-INTERNAL-001", severity="error",
                                             message=f"the channel's {name} check failed internally ({type(exc).__name__}: {_shape_reason(exc)[:200]}); its findings are missing from this receipt and must not be read as a pass",
                                             **ids))
            return default

    @staticmethod
    def _recipient_key(msg: AgentMessage) -> str:
        """The party a transmission reaches: its role and agent; the router of a channel is one party whatever agent id a
        relay names it by (a response to the router carries none)."""
        role = getattr(msg.recipient_role, "value", str(msg.recipient_role))
        return f"{role}|" if msg.recipient_role is AgentRole.ROUTER else f"{role}|{msg.recipient_agent_id or ''}"

    def _dedupe(self, msg: AgentMessage) -> list[IntegrityFinding]:
        """INT-ENV-001 for a payload already DELIVERED to this recipient on this channel. Only delivered transmissions are
        recorded (:meth:`_finish`), so a relay the channel refused is no precedent for the first legitimate one."""
        key = f"{msg.payload_sha256}|{self._recipient_key(msg)}"  # the same report forwarded to another recipient is a hand-off, not a replay
        first = self._seen_payloads.get(key)
        if first is not None:
            return [IntegrityFinding(code="INT-ENV-001", severity="warning", message="identical payload already transmitted to this recipient on this channel (replay or duplicate delivery)", message_ids=[msg.message_id, first])]
        return []

    def _record_delivery(self, msg: AgentMessage) -> None:
        self._seen_payloads.setdefault(f"{msg.payload_sha256}|{self._recipient_key(msg)}", msg.message_id)
        rid = msg.payload.get("report_id") if isinstance(msg.payload, dict) and msg.contract.startswith("specialist_report") else None
        if isinstance(rid, str):
            self.report_recipients.setdefault(rid, set()).add(self._recipient_key(msg))
        sid = msg.payload.get("synthesis_id") if isinstance(msg.payload, dict) and msg.contract.startswith("synthesis") else None
        if isinstance(sid, str):
            self.synthesis_recipients.setdefault(sid, set()).add(self._recipient_key(msg))

    def _source_findings(self, report: SpecialistReport, supplied: list[SuppliedText], *, request_text: Optional[str] = None) -> tuple[set[str], set[str], list[IntegrityFinding]]:
        """Every source reference of every claim against the supplied texts. An excerpt the
        cited document does not contain is INT-REQ-003 (error): the message says it was not
        found in the supplied texts, naming them, or where else it occurs (misattribution),
        rather than calling one document the cited one. An excerpt whose words occur but whose
        form differs (initial capital, verse line-break mark, long elision) is INT-REQ-010
        (warning): not an invented quotation. An excerpt whose words are the request's own (a
        true/false statement, a phrase of the question: "toda", "complete years") quotes the
        request and is no invented quotation: no finding, and no branch ``-SRC-001`` error for it.
        A not-found message names the supplied text that holds all of the excerpt's words but one
        or two (an altered quotation). Returns the claims so covered, the subset covered only by a
        form-difference warning (or a quotation of the request), and the findings."""
        from ..adapters.sources import nearest_text
        doc_ids = sorted(t.document_id for t in supplied)
        by_id = {t.document_id: t for t in supplied}
        covered: set[str] = set()
        not_found: set[str] = set()
        out: list[IntegrityFinding] = []
        for c in report.claims:
            checks = check_claim_sources(c, supplied)
            for ref, g in zip(c.source_refs, checks):
                if g.verified is not False:
                    continue
                detail = g.detail or ""
                if request_text and (ref.excerpt or "").strip() and g.method != "locator_exists" and _located(ref.excerpt or "", request_text):
                    covered.add(c.claim_id)  # the request's own words, quoted: located, not invented
                    continue
                ids = dict(claim_ids=[c.claim_id], report_ids=[report.report_id], agent_ids=[report.agent_id], document_ids=doc_ids)
                if g.method == "locator_exists":
                    out.append(IntegrityFinding(code="INT-REQ-003", severity="error", message=f"citation of claim {c.claim_id} to document {ref.document_id!r} cannot be verified: {detail} (supplied texts: {doc_ids})", **ids))
                elif _FORM_DIFFERS in detail:
                    out.append(IntegrityFinding(code="INT-REQ-010", severity="warning", message=f"quotation cited by claim {c.claim_id} differs only in form from the supplied text {ref.document_id!r}: {detail}; the words occur, so this is not an invented quotation", **ids))
                elif ref.document_id not in by_id:
                    out.append(IntegrityFinding(code="INT-REQ-003", severity="error", message=f"quotation cited by claim {c.claim_id} names document {ref.document_id!r}, which is not among the supplied texts {doc_ids}", **ids))
                elif not (ref.excerpt or "").strip():
                    out.append(IntegrityFinding(code="INT-REQ-003", severity="error", message=f"quotation cited by claim {c.claim_id} to document {ref.document_id!r} carries no excerpt to check", **ids))
                else:
                    elsewhere = sorted(d for d, t in by_id.items() if d != ref.document_id and locate_excerpt(ref.excerpt or "", t.text, document_id=d) is not None)
                    if elsewhere:
                        out.append(IntegrityFinding(code="INT-REQ-003", severity="error", message=f"quotation cited by claim {c.claim_id} to document {ref.document_id!r} does not occur there; its words occur in {elsewhere} (misattributed)", **ids))
                    else:
                        near, missing = nearest_text(ref.excerpt or "", by_id)
                        hint = (f"; the supplied text {near} holds all of its words but {', '.join(missing)} (an altered quotation)"
                                if near is not None and 0 < len(missing) <= 2 and len((ref.excerpt or "").split()) >= 3 else "")
                        out.append(IntegrityFinding(code="INT-REQ-003", severity="error", message=f"quotation cited by claim {c.claim_id} was not found in the supplied texts {doc_ids}{hint}", **ids))
                covered.add(c.claim_id)
                if out[-1].code == "INT-REQ-003":
                    not_found.add(c.claim_id)
        return covered, covered - not_found, out

    @staticmethod
    def _uncredited_quotations(report: SpecialistReport, supplied: list[SuppliedText], *, request_text: Optional[str] = None) -> list[IntegrityFinding]:
        """INT-REQ-003 (error) for a quotation the parser credited to no text (``sources.uncredited_assumption``, which the
        core pack reports as unverifiable, CORE-SRC-003) when texts were supplied and the quotation is refutable against
        them: its words occur in none of the supplied texts nor in the request, its sentence carries no from-memory label,
        and either a supplied text holds all of its words but one or two (an altered quotation of that text: "could mean
        that shely has been hurt"; a relayed colleague's report counts only when no other text was supplied) or its
        sentence credits it by kind to the text under analysis ("The narrator also insists that '...'", "the poem says").
        A quotation credited to another source ("One critic writes that ...", "A textbook says '...'", "'...', according to
        one report") stays unverifiable; one whose sentence credits it to no source at all (three words or more, not a
        mention of words a text lacks) is refuted as invented."""
        from ..adapters.markdown import find_quotation_spans
        from ..adapters.sources import is_peer_text, nearest_text, quotation_credit, uncredited_excerpt
        from ..branches.packs import _absent_mentions
        if not supplied and not request_text:
            return []
        # with no text supplied, the request's own words are still a text a quotation can alter (round-8 clearance c1,
        # ps-t14: "makes his heart race and his handsly sweat" of the student's scenario was only unverifiable)
        docs = {t.document_id: t for t in supplied}
        own = {d: t for d, t in docs.items() if not is_peer_text(t)}
        candidates = dict(own or docs)
        if request_text:  # the request's own words may be the ones altered ("complete years" -> "complete yearsly")
            candidates["the request"] = SuppliedText(document_id="the request", title=None, author="router", text=request_text)
        doc_ids = sorted(docs)
        out: list[IntegrityFinding] = []

        def norm(q: str) -> str:
            return q.strip().strip(".,;:!?").strip().casefold()

        def near_form(word: str, text: str) -> bool:
            # a word of the text that opens with the missing word's first four letters, within three letters of its length
            # (the text's words read once: ``_text_word_index``)
            w = word.strip("'").casefold()
            return len(w) >= 4 and any(abs(n - len(w)) <= 3 for n in _text_word_index(text)[2].get(w[:4], ()))

        # each claim's text folded once, not once for every quotation (a report holds at most 512 claims)
        folded_claims = [(x.claim_text, x.claim_text.casefold()) for x in report.claims]
        holders_of: dict[str, list[str]] = {}

        def claims_holding(key: str) -> list[str]:
            if key not in holders_of:
                holders_of[key] = sorted((text for text, folded in folded_claims if key in folded), key=len, reverse=True)
            return holders_of[key]

        for c in report.claims:
            for a in c.assumptions:
                ex = uncredited_excerpt(a)
                if not ex or _MEMORY_LABEL_RE.search(c.claim_text):
                    continue
                if any(_located(ex, t.text, t.document_id) for t in supplied) or (request_text and _located(ex, request_text)):
                    continue
                words = len(ex.split())
                near, missing, altered = None, [], False
                for d, t in candidates.items():  # the text this quotation alters: all its words but one or two (a short one: a near form)
                    _n, miss = nearest_text(ex, {d: t})
                    # a short one (one or two words) needs a near form of its missing word in the text, or, for two words, the
                    # word it holds next to a near form of the other (rule short-near-miss: «crecen amigos» for «crecen amistades»)
                    if 0 < len(miss) <= 2 and len(miss) < words and (words >= 3 or all(near_form(w, t.text) for w in miss) or (words == 2 and displaced_word(ex, t.text))) \
                            and (not altered or len(miss) < len(missing)):
                        near, missing, altered = d, miss, True
                # The sentence that carries the quotation (a parser may deliver the quotation as its own evidence claim and
                # the sentence that credits it as another claim): the longest claim text holding it, else the response.
                holders = claims_holding(norm(ex))
                sentence = holders[0] if holders else c.claim_text
                credit = None
                all_spans = find_quotation_spans(sentence)
                spans = [sp for sp in all_spans if norm(sp[2]) == norm(ex)]
                if spans:
                    credit = quotation_credit(sentence, spans[0][0], docs)
                by_kind = credit is not None and credit.generic and bool(own)
                # A quotation of three words or more that its sentence credits to no source at all, while texts of the task
                # were supplied and none holds it (nor the request), is presented as the supplied material's words: an
                # invented quotation, refuted against the texts. A quoted word the sentence says a text lacks ('never says
                # "ayudar"') is a mention, and a short scare quote stays unverifiable (CORE-SRC-003).
                mentioned = {norm(q) for q in _absent_mentions(sentence, all_spans)} if credit is None else set()
                uncredited = (credit is None and bool(own) and bool(spans) and words >= 3 and norm(ex) not in mentioned
                              and not _credits_another_source(sentence, spans[0][0], spans[0][1]))
                if not (altered or by_kind or uncredited):
                    continue
                why = (f"{'the request' if near == 'the request' else 'the supplied text ' + near} holds all of its words but {', '.join(missing)} (an altered quotation)" if altered
                       else f"the sentence credits it to {credit.phrase!r}, the text under analysis named by kind (an invented quotation)" if by_kind
                       else "its sentence credits it to no source, and none of the supplied texts nor the request holds its words (an invented quotation)")
                out.append(IntegrityFinding(code="INT-REQ-003", severity="error",
                                            message=f"quotation '{ex[:120]}' of claim {c.claim_id}, which the report credits to no text, was not found in the supplied texts {doc_ids}"
                                                    + (" nor in the request" if request_text else "") + f": {why}",
                                            claim_ids=[c.claim_id], report_ids=[report.report_id], agent_ids=[report.agent_id], document_ids=doc_ids))
        return out

    @staticmethod
    def _peer_figures(report: SpecialistReport, supplied: list[SuppliedText]) -> list[IntegrityFinding]:
        """INT-REQ-014 (warning): a claim that credits a relayed peer specialist's report ("the History specialist gives
        close to two million inhabitants": the clause after the peer's possessive, after the peer as the subject of a
        reporting verb, or after "according to" the peer, :func:`~epinoic_logic.adapters.sources.credited_spans`; a decimal
        point or an abbreviation never ends that clause) states there, outside its quotations, figures or dates (digits or
        words) that occur in no supplied text, the peer's report included, or a date the peer gives for another event
        (:func:`~epinoic_logic.integrity.ledger.credited_date_repairings`: "The History specialist dates the sonnet to
        1886" where the peer dates the sonnet 1883 and the statue's dedication 1886). Quotations of the peer are checked
        as quotations (INT-REQ-003); this names a figure misreported in an unquoted paraphrase of the colleague, shown with
        its scale word ("2.5 million"). Figures in words count (the ledger's reader)."""
        from ..adapters.sources import credited_spans
        from ..integrity.ledger import credited_date_repairings, figure_spellings, magnitude_keys
        peers = [t for t in supplied if t.document_id.startswith("peer:") or (t.author or "").endswith("-specialist")]
        if not peers:
            return []
        known: set[str] = set()
        for t in supplied:
            for _label, keys in figure_spellings(t.text):
                known |= magnitude_keys(keys)  # a peer's signed figure restated as its magnitude is the peer's figure
        out: list[IntegrityFinding] = []
        for c in _material_claims(report):
            text = blank_quotations(c.claim_text)  # quotations are checked as quotations
            spans = {p.document_id: credited_spans(text, p) for p in peers}
            credited = sorted(d for d, sp in spans.items() if sp)
            if not credited:
                continue
            stated = " ".join(text[a:b] for sp in spans.values() for a, b in sp)
            unknown = sorted({label for label, keys in figure_spellings(stated, with_scale=True) if not (keys & known)})
            ids = dict(claim_ids=[c.claim_id], report_ids=[report.report_id], agent_ids=[report.agent_id], document_ids=credited)
            if unknown:
                out.append(IntegrityFinding(code="INT-REQ-014", severity="warning", message=f"claim {c.claim_id} credits the peer report(s) {credited} but states figures or dates {unknown} that occur in neither the peer's report nor any other supplied text: a colleague's figure misreported in an unquoted paraphrase, or the agent's own unsupported figure", **ids))
                continue
            repaired = [d for p in peers if spans.get(p.document_id) for a, b in spans[p.document_id] for d in credited_date_repairings(text[a:b], p.text)]
            if repaired:
                out.append(IntegrityFinding(code="INT-REQ-014", severity="warning", message=f"claim {c.claim_id} credits the peer report(s) {credited} with a date the peer gives for another event: " + "; ".join(dict.fromkeys(repaired)) + ": a colleague's date misreported in an unquoted paraphrase", **ids))
        return out

    def _peer_documents(self, supplied: list[SuppliedText]) -> list[SuppliedText]:
        """The supplied texts that hold a peer specialist's report: a 'peer:<task>' document, a text a specialist wrote
        (its author ends in '-specialist' or ' specialist'), or, whatever the router named it, a text byte-identical to
        a report delivered on this channel (integration gate, round 1: the forwarded report supplied as 'en-report' with
        no author switched the rule off)."""
        delivered = {r.original_response for r in self.transmitted_reports.values()}
        return [t for t in supplied if t.document_id.startswith("peer:") or (t.author or "").strip().lower().endswith(("-specialist", " specialist"))
                or t.text in delivered]

    def _relayed_check_results(self, report: SpecialistReport, supplied: list[SuppliedText]) -> list[IntegrityFinding]:
        """INT-REQ-014 (warning): an agent that answers after a peer's report was given to it (:meth:`_peer_documents`)
        states, as a claim of its own, a check result of this exchange (:func:`check_result_statement`: "A formal check
        failed the report's restated 0.1 pH result", "Z3 proved the Mathematics report's speed correct", "The Mathematics
        report passed all checks", "the Mathematics report's own checks flag its written lines as not holding"). No check
        result is content of a report: a router-side receipt, an engine verdict or an invented one relayed as the agent's
        own words is a self-report, named so the router never reads it as checked (agent self-reports are advisory).
        Ordinary content about checks ("Automated checks fail when the sensor data are missing", "The receipt shows the
        payment failed") names no report or answer of the exchange and is not read as one. Every claim is read, notes
        roled 'other' included, with its quotations masked."""
        peers = self._peer_documents(supplied)
        if not peers:
            return []
        object_words = [w for t in peers for w in re.findall(r"[^\W\d_][\w'’-]*", f"{t.title or ''} {(t.author or '').replace('-', ' ')}")
                        if w.casefold() not in ("the", "report", "relayed", "through", "hub", "specialist", "answer")]
        out: list[IntegrityFinding] = []
        for c in report.claims:
            text = blank_quotations(c.claim_text)
            noun = check_result_statement(text, object_words=object_words)
            if noun is None:
                continue
            out.append(IntegrityFinding(code="INT-REQ-014", severity="warning", message=f"claim {c.claim_id} (role {c.claim_role}) states a check result credited to the system or "
                                        f"to a report ({noun!r}): a check result is no content of a report; the agent relays a router-side or invented "
                                        "outcome as its own words, a self-report the router must not read as checked",
                                        claim_ids=[c.claim_id], report_ids=[report.report_id], agent_ids=[report.agent_id]))
        return out

    def _claim_id_collisions(self, report: SpecialistReport) -> list[IntegrityFinding]:
        """INT-REQ-016 (warning): a claim id of this report that a report of ANOTHER agent already delivered on this task
        holds. The router would hold two different claims under one id, and a synthesis citing it cannot be accounted
        for (INT-LEDGER-014), so the collision is named at delivery, with both reports, for the router and the
        combinator to disambiguate before citing it. The same agent re-using its own ids is a supersession
        (INT-HANDOFF-009), and a report already held under its id (a hand-off of the same report) collides with nothing."""
        if report.report_id in self.transmitted_reports:
            return []
        mine = {c.claim_id for c in report.claims}
        held: dict[str, list[str]] = {}
        agents: set[str] = set()
        for r in self.transmitted_reports.values():
            if r.agent_id == report.agent_id:
                continue
            for c in r.claims:
                if c.claim_id in mine:
                    held.setdefault(c.claim_id, []).append(r.report_id)
                    agents.add(r.agent_id)
        if not held:
            return []
        ids = sorted(held)
        where = "; ".join(f"{cid!r} in {sorted(set(rids))}" for cid, rids in sorted(held.items())[:_MAX_NAMED]) + (f" and {len(held) - _MAX_NAMED} more" if len(held) > _MAX_NAMED else "")
        return [IntegrityFinding(code="INT-REQ-016", severity="warning",
                                 message=f"report {report.report_id!r} of agent {report.agent_id!r} delivers claim id(s) {_named(ids)} that a report of another agent already delivered on this task holds ({where}): the router now holds two different claims under one id, and a synthesis citing it cannot be accounted for by id (INT-LEDGER-014); disambiguate before citing",
                                 claim_ids=ids, report_ids=_dedupe_ids([report.report_id] + [rid for cid in ids for rid in held[cid]]), agent_ids=sorted(agents | {report.agent_id}))]

    def _channel_texts(self, supplied: list[SuppliedText]) -> dict[str, SuppliedText]:
        """Every text known on this channel: the agent's own supplied texts first, then the texts the router supplied to
        any agent of the task (a poem given to the English specialist is known when the History specialist credits it)."""
        known = {t.document_id: t for t in supplied}
        for req in self.requests.values():
            for t in req.supplied_texts:
                known.setdefault(t.document_id, t)
        for r in self.transmitted_reports.values():
            for t in r.supplied_texts:
                known.setdefault(t.document_id, t)
        return known

    def _foreign_credits(self, report: SpecialistReport, supplied: list[SuppliedText], structural=()) -> list[IntegrityFinding]:
        """INT-REQ-015: a quotation whose sentence credits it (a possessive or a crediting verb after the name:
        "Hardy's speaker himself admits that ...", "The poem says that ...") to a source the agent was NOT supplied (a
        text the router supplied to another agent of the task, or a text named by kind, "the poem", when none was
        supplied to this agent), while its words occur, among the agent's supplied texts, only in a relayed peer
        specialist's report and not in the credited text (or, for a text named by kind, in the peer's own prose rather
        than in a quotation the peer made): a colleague's words presented as the source's. An error, since a peer report is
        on one side. A credit to a supplied text is the packs' rule (CORE-SRC-005, ES-SRC-008), and a claim a pack already
        named under CORE-SRC-005 is not named again."""
        from ..adapters.markdown import find_quotation_spans
        from ..adapters.sources import is_peer_text, peer_prose_span, quotation_credit, strip_trailing_punctuation
        peers = [t for t in supplied if is_peer_text(t)]
        if not peers:
            return []
        supplied_ids = {t.document_id for t in supplied}
        known = self._channel_texts(list(supplied))
        already = {cid for sf in structural if sf.code == "CORE-SRC-005" for cid in sf.claim_ids}
        out: list[IntegrityFinding] = []
        seen: set[tuple[str, str]] = set()
        for c in report.claims:
            if c.claim_id in already:
                continue
            for start, _end, inner in find_quotation_spans(c.claim_text):
                q = strip_trailing_punctuation(inner)
                if len(q) < 4 or not re.search(r"[^\W\d_]", q) or (c.claim_id, q) in seen:
                    continue
                located = [t for t in supplied if _located(q, t.text, t.document_id)]
                if not located or not all(is_peer_text(t) for t in located):
                    continue
                credit = quotation_credit(c.claim_text, start, known)
                if credit is None or (credit.document_id is not None and credit.document_id in supplied_ids):
                    continue
                if credit.document_id is not None:
                    doc = known[credit.document_id]
                    if _located(q, doc.text, doc.document_id):
                        continue  # the credited text holds the words: the credit is right, whoever supplied them
                    label = f"{credit.document_id} ({', '.join(x for x in (doc.author, doc.title) if x)}), a text of this task that was not supplied to {report.agent_id!r} and does not hold these words"
                else:
                    if not any(peer_prose_span(q, t) for t in located):
                        continue  # the peer itself quoted these words from some text: the credit cannot be judged here
                    label = f"a text named by kind; none was supplied to {report.agent_id!r}"
                seen.add((c.claim_id, q))
                peer_ids = [t.document_id for t in located]
                carriers = [x.claim_id for x in report.claims if x.claim_id != c.claim_id and any(_norm_text(r.excerpt or "") == _norm_text(q) for r in x.source_refs)]
                out.append(IntegrityFinding(code="INT-REQ-015", severity="error",
                                            message=f"claim {c.claim_id} credits the quotation '{q[:120]}' to {credit.phrase!r} ({label}), but its words occur only in {peer_ids}, a relayed specialist's report: a colleague's words presented as the source's (misattributed)",
                                            claim_ids=[c.claim_id] + carriers, report_ids=[report.report_id], agent_ids=[report.agent_id],
                                            document_ids=sorted(set(peer_ids) | ({credit.document_id} if credit.document_id else set()))))
        return out

    def _fold_findings(self, report: SpecialistReport, supplied: list[SuppliedText]) -> list[IntegrityFinding]:
        """INT-REQ-013 (warning): the branch adapter folded the claims beyond the contract limit into one tail claim
        (its ``unresolved_issues`` say so), so those sentences were neither roled nor checked individually. The finding
        names how many claims and how many quotations went unchecked, and which of those quotations occur in no
        supplied text, so an invented quotation placed after the limit does not cross the hub silently. The quotations
        are read from the original response (the tail claim's text is cut to the contract length): every quoted span
        that no claim before the tail carries is an unchecked quotation."""
        from ..adapters.markdown import find_quotation_spans
        out: list[IntegrityFinding] = []
        for issue in report.unresolved_issues:
            m = _FOLDED_TAIL_RE.search(issue)
            if m is None:
                continue
            tail_id = m.group("tail")
            head_text = " ".join(c.claim_text for c in report.claims if c.claim_id != tail_id)
            cited = {(ref.excerpt or "").strip() for c in report.claims if c.claim_id != tail_id for ref in c.source_refs}
            quotes = _dedupe_ids(inner.strip() for _s, _e, inner in find_quotation_spans(report.original_response)
                                 if inner.strip() and inner.strip() not in head_text and inner.strip() not in cited)
            unlocated = [q for q in quotes if not any(_located(q, t.text, t.document_id) for t in supplied)] if supplied else list(quotes)
            where = "in no supplied text" if supplied else "against no text (none was supplied)"
            detail = f"; {len(quotes)} quotation(s) in the merged text were not checked" + (f", of which {len(unlocated)} occur {where}: {[q[:60] for q in unlocated[:_MAX_NAMED]]}" if unlocated else (f" (all {len(quotes)} occur in a supplied text)" if quotes else ""))
            out.append(IntegrityFinding(code="INT-REQ-013", severity="warning",
                                        message=f"the branch adapter merged {m.group('n')} claims beyond the claim limit ({m.group('limit')}) into claim {tail_id!r} without roling or checking them individually{detail}; the router must not treat the merged sentences as checked",
                                        claim_ids=[tail_id], report_ids=[report.report_id], agent_ids=[report.agent_id], document_ids=sorted(t.document_id for t in supplied)))
        return out

    @staticmethod
    def _hook(call, fallback):
        """A hub hook's answer, or ``fallback`` when the hook fails: a hook only ever refines a heuristic."""
        try:
            return call()
        except Exception:
            return fallback

    @staticmethod
    def _no_answer(report: SpecialistReport, view=None) -> list[IntegrityFinding]:
        """INT-REQ-012 (error): the response carries no material claim (every claim is a note, a label or a self-report)
        or its answer proper has no words, so it addresses no request item whatever words its notes share with them.
        ``view``: the branch's word-count view (STEM: a maths span or code block is one word)."""
        material = _material_claims(report)
        answer_words, note_words = count_answer_words(report.original_response, view=view)
        if material and answer_words > 0:
            return []
        why = []
        if not material:
            why.append(f"none of its {len(report.claims)} claim(s) is material (every claim is roled 'other': a note, a label or a self-report)" if report.claims else "it carries no claim")
        if answer_words == 0:
            why.append(f"its answer proper has 0 words ({note_words} words of note or meta-text blocks)")
        return [IntegrityFinding(code="INT-REQ-012", severity="error", message="the response carries no answer: " + " and ".join(why) + "; no request item counts as addressed",
                                 claim_ids=[c.claim_id for c in report.claims], report_ids=[report.report_id], agent_ids=[report.agent_id])]

    @staticmethod
    def _request_echo(req: TaskRequest, report: SpecialistReport, supplied: list[SuppliedText] = ()) -> Optional[IntegrityFinding]:
        """A response that restates the request instead of answering it (INT-REQ-011). Words are compared on light
        stems (``-s``, ``-es``, ``-ed``, ``-ing`` stripped), so an inflected restatement is still a restatement, and the
        overlap is measured on content stems (function words such as "in", "is", "through" set aside): its stemmed text
        is contained in the request's, or at least 90% of its distinct stems occur in the request and it
        is no longer than 1.5 times the request, or at least 75% do, it is no longer than 2 times the request and it
        quotes the request's own words as if they were the text's (a quotation whose words all occur in the request but
        in no supplied text). The quoted rule is evaluated whatever the plain rule's length cap says."""
        from ..adapters.markdown import find_quotation_spans
        resp_tokens = [light_stem(t) for t in _tokens(report.original_response)]
        ask_tokens = [light_stem(t) for t in _tokens(req.user_input)]
        if not resp_tokens or not ask_tokens:
            return None
        resp, ask = " ".join(resp_tokens), " ".join(ask_tokens)
        how: Optional[str] = None
        if resp == ask or resp in ask:
            how = "its normalised text is the request's own text" if resp == ask else "its normalised text is contained in the request"
        else:
            ask_set = set(ask_tokens)
            distinct = {t for t in resp_tokens if t not in _ECHO_FUNCTION} or set(resp_tokens)
            overlap = len(distinct & ask_set) / len(distinct)
            ratio = len(resp_tokens) / len(ask_tokens)
            if overlap >= _ECHO_OVERLAP and ratio <= _ECHO_LENGTH_RATIO:
                how = f"{overlap:.0%} of its distinct words (content light stems; function words aside) occur in the request and it is {ratio:.2f}x the request's length (no longer than {_ECHO_LENGTH_RATIO}x)"
            elif overlap >= _ECHO_OVERLAP_QUOTED and ratio <= _ECHO_QUOTED_LENGTH_RATIO:
                echoed_quotes = [inner for _s, _e, inner in find_quotation_spans(report.original_response)
                                 if _tokens(inner) and set(light_stem(t) for t in _tokens(inner)) <= ask_set and not any(_located(inner, t.text, t.document_id) for t in supplied)]
                if echoed_quotes:
                    how = (f"{overlap:.0%} of its distinct words (content light stems; function words aside) occur in the request, it is {ratio:.2f}x the request's length (no longer than {_ECHO_QUOTED_LENGTH_RATIO}x), "
                           f"and it quotes the request's own words as if they were the text's ({[q[:60] for q in echoed_quotes[:_MAX_NAMED]]} occur in the request and in no supplied text)")
        if how is None:
            return None
        return IntegrityFinding(code="INT-REQ-011", severity="error", message=f"the response restates the request instead of answering it ({how}); no request item counts as addressed", claim_ids=[c.claim_id for c in report.claims], report_ids=[report.report_id], agent_ids=[report.agent_id])

    def _coverage(self, req: TaskRequest, report: SpecialistReport, *, echoed: bool = False, hooks=None, profile_key: str = "") -> list[CoverageRecord]:
        """Which request items the report addresses (a note never addresses one). A lettered or numbered item ("(b) Describe
        ...", "1. ¿Cómo era ...?") is compared per part when the answer labels its parts with the request's labels: the
        claims under the same label address it, so a reply that answers part (a) alone leaves (b) to (d) unaddressed
        whatever words they share, and "1. Basura y cristales rotos." addresses item 1 in any language. Otherwise the
        lexical heuristic: enough shared content terms with one material claim, or with the material claims of one
        paragraph together (a paragraph that answers a guiding question need not repeat its words in one sentence); a
        guiding, essay or research question is answered by a point, thesis or judgement claim that takes up its terms.
        ``hooks`` (a branch's hub hooks; the STEM branches) lend each claim extra words (STEM: the dimensions of its
        quantities), read wherever the claim's own words are. An answer that declines the deliverable, or defers it to the
        student's reply (:func:`withheld_deliverable`, read from the report itself, so the transfer auditor's re-run of this
        rule gives the same records), addresses no item, whatever words it shares with them (round-8 clearance c1: ge-t14's
        decline and ps-p8d's plan were read as answering every item)."""
        out: list[CoverageRecord] = []
        if withheld_deliverable(report.original_response) is not None:
            return [CoverageRecord(item_id=item.item_id, addressed=False, addressed_by_claim_ids=[], method="lexical_heuristic") for item in req.items]
        material = _material_claims(report)
        sections = _answer_sections(report.original_response)
        section_of = _claim_sections(report.original_response, sections, material) if sections else {}
        answer_labels = {lab for _start, labels in sections for lab in labels}
        item_labels = {part_label(i.text) or question_label(i.text) for i in req.items} - {None}
        by_part = bool(item_labels & answer_labels)  # the answer labels its parts (or its questions) as the request does
        claim_terms: dict[str, set[str]] = {}
        for c in material:
            terms = _terms(c.claim_text)
            if hooks is not None:  # the branch's extra words for this claim (STEM: the dimensions of its quantities)
                extra = self._hook(lambda: hooks.coverage_terms(c.claim_text, report.original_response, req.user_input, profile_key), frozenset())
                terms = terms | _terms(" ".join(sorted(extra)))
            claim_terms[c.claim_id] = terms
        groups: dict[str, set[str]] = {}
        for c in material:
            groups.setdefault(_paragraph_key(c.claim_id), set()).update(claim_terms[c.claim_id])
        for item in req.items:
            if echoed:  # a restated request addresses nothing, whatever words it shares with the items
                out.append(CoverageRecord(item_id=item.item_id, addressed=False, addressed_by_claim_ids=[], method="lexical_heuristic"))
                continue
            lab = part_label(item.text) or question_label(item.text)
            if by_part and lab is not None:
                hits = [c.claim_id for c in material if lab in section_of.get(c.claim_id, ())]
                out.append(CoverageRecord(item_id=item.item_id, addressed=bool(hits), addressed_by_claim_ids=hits, method="part_label"))
                continue
            it = _terms(_ITEM_LABEL_RE.sub("", item.text))
            need = max(1, min(2, len(it) // 3))
            hits = [c.claim_id for c in material if it and len(it & claim_terms[c.claim_id]) >= need]  # a note never addresses an item
            if it and not hits:  # a paragraph's claims together
                hits = [c.claim_id for c in material if len(it & groups.get(_paragraph_key(c.claim_id), set())) >= need]
            if it and not hits and _ITEM_LABEL_RE.match(item.text):
                # A guiding (essay, research) question frames the whole answer: a point, thesis or judgement claim that
                # takes up its terms answers it, even when no sentence repeats enough of its words.
                hits = [c.claim_id for c in material if c.claim_role in ("point", "thesis", "judgement") and it & claim_terms[c.claim_id]]
            out.append(CoverageRecord(item_id=item.item_id, addressed=bool(hits) or not it, addressed_by_claim_ids=hits, method="lexical_heuristic"))
        return out

    def _constraints(self, req: TaskRequest, report: SpecialistReport, view=None) -> tuple[list[ConstraintResult], list[str]]:
        results: list[ConstraintResult] = []
        # A bound set on a deliverable the answer declines (round-8 clearance c1, ge-t14: an academic-integrity decline of 639
        # words against "about 900") does not apply to the decline: it is recorded not applicable (satisfied None, no formal
        # result, no INT-REQ-005), naming the declining sentence, and the request's items are INT-REQ-004 naming it. The
        # transfer auditor accepts exactly this record exactly when ``withheld_deliverable`` reads a decline in the journaled
        # response (``overseer.checks.formal.declined_bound``), so the receipt and the audit agree.
        withheld = withheld_deliverable(report.original_response)
        declined = withheld[1] if withheld is not None and withheld[0] == "declined" else None
        formal_ids: list[str] = []
        measures: dict[tuple, tuple[int, int, int, str]] = {}

        def word_measure(c: Constraint) -> tuple[int, int, int, str]:
            """``(answer words, note words, exempt words, scope note)`` for a word bound: notes left out, and the working
            and the diagram too when the request sets them outside the bound ("plus working and your diagram"), measured on
            the branch's word-count view when it lends one (STEM: a maths span or a code block is one word), over each part
            of the answer for a bound the request sets on each part (``request_parser.bound_word_measure``, which the
            transfer auditor's recount calls too)."""
            key = (tuple(sorted(c.excludes)), c.kind if per_part_bound(c) else None)
            if key not in measures:
                measures[key] = bound_word_measure(report.original_response, c, request_text=req.user_input, view=view, measure=measure_answer_words)
            return measures[key]
        words, meta_words, _none, _scope = word_measure(Constraint(constraint_id="all", kind="max_words", text="all"))
        paras = count_paragraphs(report.original_response)
        # A minimum and a maximum stated by one span ("about 250 words", "between 300 and 400 words", "exactly 3
        # paragraphs") are decided by ONE range problem when the measurement lies within both: each constraint cites that
        # signed result. Only a measurement outside the range is decided side by side, to say which bound it crosses. A pair
        # set on each part is measured on two parts (the longest and the shortest), so it is always decided side by side.
        ranged: dict[str, VerificationResult] = {}
        for unit in ("words", "paragraphs"):
            spans: dict[str, dict[str, Constraint]] = {}
            for c in req.constraints:
                if c.kind in (f"min_{unit}", f"max_{unit}") and c.value is not None and not per_part_bound(c):
                    spans.setdefault(c.text, {})[c.kind[:3]] = c
            for pair in spans.values():
                if declined is not None:
                    break
                measured = word_measure(next(iter(pair.values())))[0] if unit == "words" else paras
                if "min" in pair and "max" in pair and pair["min"].value.isdecimal() and pair["max"].value.isdecimal() and int(pair["min"].value) <= measured <= int(pair["max"].value):
                    res = self._formal_range(req, pair["min"], pair["max"], measured)  # the engine decides; the comparison only chooses the problem
                    if res.status is S.ENTAILED:
                        ranged[pair["min"].constraint_id] = ranged[pair["max"].constraint_id] = res
        for c in req.constraints:
            if c.kind in ("max_words", "min_words", "max_paragraphs", "min_paragraphs") and c.value is not None:
                is_words = c.kind.endswith("words")
                c_words, c_notes, c_exempt, c_scope = word_measure(c) if is_words else (words, meta_words, 0, "")
                measured = c_words if is_words else paras
                if declined is not None:
                    results.append(ConstraintResult(constraint_id=c.constraint_id, satisfied=None, method="not_checkable",
                                                    detail=truncate(f"{DECLINED_BOUND_PREFIX} ({declined[:160]!r}); measured {measured} "
                                                                    f"{'words' if is_words else 'paragraphs'}; bound {c.kind} {c.value}", 2000)))
                    continue
                res = ranged.get(c.constraint_id) or self._formal_bound(req, c, measured)
                if res.result_id not in formal_ids:
                    formal_ids.append(res.result_id)
                sat = True if res.status is S.ENTAILED else False if res.status is S.COUNTEREXAMPLE else None
                excluded = f" ({c_notes} words of note or meta-text blocks excluded, as for paragraphs)" if is_words and c_notes else ""
                if is_words and c.excludes:
                    excluded += f" (prose only: {c_exempt} words of {' and '.join(c.excludes)} excluded, as the request sets them outside the bound)"
                if is_words and c_scope:
                    excluded += f" ({c_scope})"
                band = (" (the request states a band around a target length, and the measure lies within a quarter of the target, so it is a warning)"
                        if sat is False and about_band(c) and word_bound_severity(c, measured) == "warning" else "")
                results.append(ConstraintResult(constraint_id=c.constraint_id, satisfied=sat, method="formal",
                                                detail=truncate(f"measured {measured} {'words' if is_words else 'paragraphs'}{excluded}; bound {c.kind} {c.value}; "
                                                                f"solver {res.status.value}{band}", 2000),
                                                formal_result_id=res.result_id, formal_status=res.status.value))
            elif c.kind == "must_cite_supplied_text":
                results.append(self._citation_result(c, req, report))
            else:
                results.append(ConstraintResult(constraint_id=c.constraint_id, satisfied=None, method="not_checkable", detail="constraint kind not checkable by code"))
        return results, formal_ids

    @staticmethod
    def _citation_result(c: Constraint, req: TaskRequest, report: SpecialistReport) -> ConstraintResult:
        """``must_cite_supplied_text``: satisfied by a claim that carries a source reference (a quotation the parser
        located), or by evidence the answer cites the supplied texts as it was asked to (``channel.citations``, round-8
        clearance c1, breadth F13/F14): a locator the supplied texts resolve ("(paragraph 1)", "(Table 1)") when the request
        asks for citations, figures from a supplied table, or a code span found in supplied code. A request that asks for
        quotations ("quote", "quotations") is not satisfied by a bare locator."""
        if any(cl.source_refs for cl in report.claims):
            return ConstraintResult(constraint_id=c.constraint_id, satisfied=True, method="deterministic", detail="at least one claim carries a source reference")
        quotation_asked = bool(re.search(r"\bquot", c.text or "", re.IGNORECASE))
        evidence = citation_evidence(report.original_response or "", list(req.supplied_texts) or list(report.supplied_texts), quotation_asked=quotation_asked)
        if evidence is not None:
            return ConstraintResult(constraint_id=c.constraint_id, satisfied=True, method="deterministic",
                                    detail=truncate(f"no claim carries a quotation's source reference, but the answer {evidence.describe()}", 300))
        detail = "no claim carries a source reference" + (" and the answer cites no supplied text by locator, table figure or quoted code" if not quotation_asked
                                                          else " and the answer quotes no supplied text (no quotation, table figure or quoted code; a locator is no quotation)")
        return ConstraintResult(constraint_id=c.constraint_id, satisfied=False, method="deterministic", detail=detail)

    def _formal_range(self, req: TaskRequest, low: Constraint, high: Constraint, measured: int) -> VerificationResult:
        """Encode 'low <= measured <= high' as one IR entailment (a signed, bound result both constraints cite)."""
        problem = Problem.model_validate({
            "problem_id": f"constraint-{low.constraint_id}-{high.constraint_id}-{uuid.uuid4().hex[:8]}", "request_id": req.request_id,
            "claim_id": f"constraint:{low.constraint_id}+{high.constraint_id}", "query": "entailment",
            "symbols": [{"name": "n", "sort": "Int", "meaning": f"measured count for {low.kind} and {high.kind}", "grounding": {"kind": "supplied_text", "verified": True}}],
            "premises": [{"id": "MEASURED", "expr": {"op": "eq", "left": {"op": "var", "name": "n"}, "right": {"op": "int", "value": str(measured)}}, "label": f"response has {measured}", "grounding": {"kind": "supplied_text", "verified": True}}],
            "conclusion": {"id": "BOUND", "expr": {"op": "and", "args": [{"op": "ge", "left": {"op": "var", "name": "n"}, "right": {"op": "int", "value": low.value}},
                                                                         {"op": "le", "left": {"op": "var", "name": "n"}, "right": {"op": "int", "value": high.value}}]},
                           "label": low.text, "grounding": {"kind": "task_setting", "verified": True}},
        })
        return verify(problem, self.config, signing_key=self.key, key_id=self.key_id, diagnose=False)  # a code-built check

    def _formal_bound(self, req: TaskRequest, c: Constraint, measured: int) -> VerificationResult:
        """Encode 'measured <op> bound' as an IR entailment so the check is a signed, bound result."""
        op = {"max_words": "le", "min_words": "ge", "max_paragraphs": "le", "min_paragraphs": "ge"}[c.kind]
        problem = Problem.model_validate({
            "problem_id": f"constraint-{c.constraint_id}-{uuid.uuid4().hex[:8]}", "request_id": req.request_id, "claim_id": f"constraint:{c.constraint_id}", "query": "entailment",
            "symbols": [{"name": "n", "sort": "Int", "meaning": f"measured count for {c.kind}", "grounding": {"kind": "supplied_text", "verified": True}}],
            "premises": [{"id": "MEASURED", "expr": {"op": "eq", "left": {"op": "var", "name": "n"}, "right": {"op": "int", "value": str(measured)}}, "label": f"response has {measured}", "grounding": {"kind": "supplied_text", "verified": True}}],
            "conclusion": {"id": "BOUND", "expr": {"op": op, "left": {"op": "var", "name": "n"}, "right": {"op": "int", "value": c.value}}, "label": c.text, "grounding": {"kind": "task_setting", "verified": True}},
        })
        return verify(problem, self.config, signing_key=self.key, key_id=self.key_id, diagnose=False)  # a code-built check

    def _supersession(self, report: SpecialistReport, findings: list[IntegrityFinding]) -> None:
        """An agent that re-states claims it already transmitted on this task supersedes its
        earlier statements: the router is told (INT-HANDOFF-009), the earlier formalizations of
        those claims leave the cross-agent pool, so a later report is cross-checked only on what
        it formalizes now, and every copy of the superseded report still in circulation is named
        (INT-HANDOFF-014): the router's forwards of it and the reports that quote it as a peer
        document, whose excerpts are re-checked against the current text.

        Overlap is decided on content, not on positional ids alone: a claim is re-stated when its
        text equals an earlier claim's (under the same or another id) and revised when it keeps an
        earlier id with another text. A response that restates the request (INT-REQ-011) or
        carries no material claim (INT-REQ-012) answers nothing and never supersedes a report."""
        if any(f.code in ("INT-REQ-011", "INT-REQ-012") for f in findings) or not _material_claims(report):
            return
        incoming = {c.claim_id: _norm_text(c.claim_text) for c in report.claims}
        restated: set[str] = set()
        revised: set[str] = set()
        earlier: list[str] = []
        for r in self.transmitted_reports.values():
            if r.agent_id != report.agent_id or r.report_id == report.report_id:
                continue
            old = {c.claim_id: _norm_text(c.claim_text) for c in r.claims}
            old_texts = set(old.values())
            same_text = {cid for cid, text in incoming.items() if text in old_texts}
            same_id = {cid for cid in incoming if cid in old and incoming[cid] != old[cid]}
            if same_text or same_id:
                earlier.append(r.report_id)
                restated |= same_text
                revised |= same_id
        earlier = sorted(earlier)
        stale = sorted(cid for cid in incoming if cid in self.formalized_by and self.formalized_by[cid][0] == report.agent_id and self.formalized_by[cid][1] != report.report_id)
        if earlier:
            overlap = sorted(restated | revised)
            what = []
            if restated:
                what.append(f"re-stating claims {sorted(restated)[:8]} (same text)")
            if revised:
                what.append(f"revising claims {sorted(revised)[:8]} (same id, changed text)")
            findings.append(IntegrityFinding(code="INT-HANDOFF-009", severity="warning",
                                             message=f"agent {report.agent_id} delivered a further report for this task {' and '.join(what)} of its earlier report(s) {earlier}; the later report supersedes them and their earlier formalizations leave the cross-agent pool",
                                             agent_ids=[report.agent_id], report_ids=[report.report_id] + earlier, claim_ids=overlap))
            for old_id in earlier:
                self.superseded[old_id] = report.report_id
                findings.extend(self._in_circulation(self.transmitted_reports[old_id], report))
        for cid in stale:
            self.formalized.pop(cid, None)
            self.formalized_by.pop(cid, None)
            self.ambiguous_pooled.discard(cid)

    def _in_circulation(self, old: SpecialistReport, new: SpecialistReport) -> list[IntegrityFinding]:
        """INT-HANDOFF-014 for a superseded report that was forwarded or is quoted as a peer document.
        Each excerpt a quoting report cites from it is re-checked: one located in the superseded text
        but not in the current one "no longer occurs"; one located in neither "was never located".
        Identifier lists are deduplicated (several reports of one quoting agent may cite the same claim ids)."""
        forwards = self.forwards.get(old.report_id, [])
        quoting: list[tuple[SpecialistReport, list[str]]] = []
        for r in self.transmitted_reports.values():
            if r.report_id in (old.report_id, new.report_id) or r.agent_id == old.agent_id:
                continue
            docs = sorted(t.document_id for t in r.supplied_texts if t.text == old.original_response)
            if docs:
                quoting.append((r, docs))
        if not forwards and not quoting:
            return []
        gone: list[str] = []
        never: list[str] = []
        for r, docs in quoting:
            for c in r.claims:
                refs = [ref for ref in c.source_refs if ref.document_id in docs and (ref.excerpt or "").strip()]
                if not refs:
                    continue
                for ref in refs:
                    in_new = _located(ref.excerpt or "", new.original_response)
                    if in_new:
                        continue
                    (gone if _located(ref.excerpt or "", old.original_response) else never).append(c.claim_id)
        gone, never = _dedupe_ids(gone), [cid for cid in _dedupe_ids(never) if cid not in gone]
        parts = [f"report {old.report_id!r} of agent {old.agent_id!r} is superseded by {new.report_id!r} but remains in circulation"]
        if forwards:
            parts.append(f"forwarded by the router to {sorted({a for a, _ in forwards})} (messages {_dedupe_ids(m for _, m in forwards)})")
        if quoting:
            parts.append(f"supplied as document(s) {sorted({d for _, ds in quoting for d in ds})} to report(s) {_dedupe_ids(r.report_id for r, _ in quoting)}")
            if gone:
                parts.append(f"excerpts cited by claims {gone} occurred in the superseded report and no longer occur in the current report")
            if never:
                parts.append(f"excerpts cited by claims {never} were never located in the superseded report either (not a consequence of the supersession)")
            if not gone and not never:
                parts.append("every excerpt those reports cite still occurs in the current report")
        return [IntegrityFinding(code="INT-HANDOFF-014", severity="warning", message="; ".join(parts), claim_ids=gone + never,
                                 report_ids=_dedupe_ids([old.report_id, new.report_id] + [r.report_id for r, _ in quoting]), agent_ids=sorted({old.agent_id} | {a for a, _ in forwards} | {r.agent_id for r, _ in quoting}),
                                 message_ids=_dedupe_ids(m for _, m in forwards), document_ids=sorted({d for _, ds in quoting for d in ds}))]

    def _with_report_ids(self, findings: list[IntegrityFinding]) -> list[IntegrityFinding]:
        """Cross-agent findings name the reports whose formalizations they concern, and say
        when a pooled claim's translation was ambiguous (its formalization is one assumed reading)."""
        out: list[IntegrityFinding] = []
        for f in findings:
            if f.claim_ids and not f.report_ids:
                rids = sorted({self.formalized_by[cid][1] for cid in f.claim_ids if cid in self.formalized_by})
                if rids:
                    f = f.model_copy(update={"report_ids": rids, "agent_ids": sorted(set(f.agent_ids) | {self.formalized_by[cid][0] for cid in f.claim_ids if cid in self.formalized_by})})
            if f.code.startswith(("INT-GLOSSARY", "INT-CONFLICT")):
                assumed = sorted(set(f.claim_ids) & self.ambiguous_pooled)
                if assumed and "AMBIGUOUS_TRANSLATION" not in f.message:
                    f = f.model_copy(update={"message": f"{f.message} (claims {assumed} are AMBIGUOUS_TRANSLATION: their pooled formalization is one assumed reading, not a fixed one)"})
            out.append(f)
        return out

    @staticmethod
    def _stale_translation(claim: ClaimRecord, report: SpecialistReport, out: ClaimVerificationOutcome) -> Optional[IntegrityFinding]:
        """INT-STALE-011: an outcome whose translation does not bind to the claim as transmitted
        (another claim id, request, report, or a translation produced for another text)."""
        tr = out.translation
        why: list[str] = []
        if out.claim_id != claim.claim_id or tr.claim_id != claim.claim_id:
            why.append("claim id")
        if out.request_id != report.request_id or tr.request_id != report.request_id:
            why.append("request id")
        if out.report_id != report.report_id or tr.report_id != report.report_id:
            why.append("report id")
        if tr.claim_text_sha256 is not None and tr.claim_text_sha256 != sha256_text(claim.claim_text):
            why.append("claim text (the translation was produced for a different text of this claim)")
        if not why:
            return None
        return IntegrityFinding(code="INT-STALE-011", severity="error", message=f"translation outcome for claim {claim.claim_id} does not bind to the claim as transmitted ({'; '.join(why)}); it is stale and is neither delivered nor pooled", claim_ids=[claim.claim_id], report_ids=[report.report_id], agent_ids=[report.agent_id])

    @staticmethod
    def _task_record(req: Optional[TaskRequest]) -> Optional[TaskRecord]:
        """The task record of the request a report answers (its request text as the router issued it), or None."""
        if req is None or not req.user_input:
            return None
        try:
            return TaskRecord.of(req.task_id, req.request_id, req.user_input)
        except ValidationError:
            return None

    def _verify_claims(self, report: SpecialistReport, findings: list[IntegrityFinding], *, pool: bool = True,
                       task: Optional[TaskRecord] = None) -> list[ClaimVerificationOutcome]:
        """Verify every claim through the injected translator; with ``pool`` the formalizations join the cross-agent
        pool (an echo of the request is verified for the record but never pooled). A verifier that declares a ``task``
        parameter receives ``task`` (the record of the request the report answers) for each claim of that task and
        request; any other verifier is called as ``fn(claim, report)``."""
        outcomes: list[ClaimVerificationOutcome] = []
        if self.verify_claim_fn is None:
            return outcomes
        with_task = task is not None and _accepts_task(self.verify_claim_fn)
        contributed = 0
        for c in report.claims:
            try:
                if with_task and c.task_id == task.task_id and c.request_id == task.request_id:  # type: ignore[union-attr]
                    out = self.verify_claim_fn(c, report, task=task)
                else:
                    out = self.verify_claim_fn(c, report)
            except Exception as exc:  # the channel never drops a message because verification crashed
                findings.append(IntegrityFinding(code="INT-REQ-006", severity="warning", message=f"claim verification failed internally for {c.claim_id}: {type(exc).__name__}", claim_ids=[c.claim_id]))
                continue
            if out is CLAIM_OUT_OF_SCOPE:
                continue  # the verifier says the claim is outside what it was asked to check (a test harness's scope)
            if out is None:
                # a verifier that returns nothing (a deadline or budget reached, no translation served) leaves the claim
                # unchecked: a material claim the deterministic eligibility rules would formalize is named NOT_ATTEMPTED, so
                # the receipt never reads as a clean acceptance of a claim no check decided (integration gate, round 1)
                if c.materiality == "material" and self._deterministically_eligible(c):
                    findings.append(self._not_attempted(c, report))
                continue
            stale = self._stale_translation(c, report, out)
            if stale is not None:
                findings.append(stale)
                continue
            outcomes.append(out)
            if out.translation.problem is not None and pool:
                self.formalized[c.claim_id] = out.translation.problem
                self.formalized_by[c.claim_id] = (report.agent_id, report.report_id)
                if out.translation.status is TranslationStatus.AMBIGUOUS_TRANSLATION:
                    self.ambiguous_pooled.add(c.claim_id)
                else:
                    self.ambiguous_pooled.discard(c.claim_id)
                contributed += 1
            # INT-REQ-007 charges the claim's premises only when the outcome shows the inconsistency (an engine result the
            # composer rejected is displayed INTERNAL_ERROR: nothing of it is charged to the specialist).
            if out.verification is not None and out.verification.status is S.INCONSISTENT_PREMISES and out.display_status in (S.INCONSISTENT_PREMISES, S.AMBIGUOUS_TRANSLATION):
                findings.append(self._inconsistent_premises(c, out))
            elif out.display_status is not S.NOT_ELIGIBLE and not is_definitive(out.display_status):
                findings.append(self._not_verified(c, out))
        if contributed and len(self.formalized) >= 2:  # only a report that formalized something can be party to a conflict
            try:
                res, f = check_cross_report_consistency(list(self.formalized.values()), request_id=self.plan.request_id, config=self.config, signing_key=self.key, assumed_readings=frozenset(self.ambiguous_pooled))
            except Exception as exc:  # the outcomes above are kept; the router is told the joint check is missing
                findings.append(IntegrityFinding(code="INT-INTERNAL-001", severity="error", message=f"the channel's cross-agent consistency check failed internally ({type(exc).__name__}); contradictions with other agents' claims were not checked on this receipt",
                                                 report_ids=[report.report_id], agent_ids=[report.agent_id]))
                return outcomes
            f = self._with_report_ids(f)
            self.conflicts_seen.extend((frozenset(x.claim_ids), x.formal_result_id) for x in f if x.code == "INT-CONFLICT-001")
            # a glossary warning about two claims of other reports was named on the receipt that pooled them; this receipt
            # carries only those that name one of its own claims (round-8 clearance c1: bm-p8a's receipt carried eleven warnings
            # about pairs of the Economics specialist's claims). Contradictions and every other pool finding stay as they are.
            own = {c.claim_id for c in report.claims}
            findings.extend(x for x in f if x.code != "INT-GLOSSARY-005" or set(x.claim_ids) & own)
        return outcomes

    @staticmethod
    def _deterministically_eligible(claim: ClaimRecord) -> bool:
        """Whether the deterministic eligibility rules and the claim's subject policy make ``claim`` eligible for the
        formal check (no model: ``decide_eligibility`` narrowed by ``apply_subject_policy``, as the pipeline and the
        delivery policy decide it). A decision that cannot be made is never "not eligible"."""
        try:
            from ..translate.eligibility import decide_eligibility
            from ..translate.pipeline import apply_subject_policy
            from ..translate.subjects import resolve_profile
            return bool(apply_subject_policy(decide_eligibility(claim), resolve_profile(claim.subject)).eligible)
        except Exception:
            return True

    @staticmethod
    def _not_attempted(claim: ClaimRecord, report: SpecialistReport) -> IntegrityFinding:
        """INT-REQ-006 (warning): a material claim the deterministic eligibility rules make eligible has no outcome (the
        verifier returned none: a translation budget or deadline reached, or no translation served). The claim is
        NOT_ATTEMPTED: no check decided it, so the router must not read it as checked, and the receipt is never a clean
        acceptance on its account."""
        return IntegrityFinding(code="INT-REQ-006", severity="warning",
                                message=f"claim {claim.claim_id} is material and eligible for the formal check (deterministic eligibility under its subject policy), "
                                        "but its verification produced no outcome: NOT_ATTEMPTED (no translation or engine result reached this receipt), "
                                        "so the router must not read the claim as checked", claim_ids=[claim.claim_id],
                                report_ids=[report.report_id], agent_ids=[report.agent_id])

    @staticmethod
    def _not_verified(claim: ClaimRecord, out: ClaimVerificationOutcome) -> IntegrityFinding:
        """INT-REQ-006 (warning): a claim whose outcome is displayed with a status that is no verdict (INVALID_FORMALIZATION,
        AMBIGUOUS_TRANSLATION, UNSUPPORTED, TIMEOUT, UNKNOWN, INTERNAL_ERROR; NOT_ELIGIBLE is no attempt and is not named),
        whatever the engine returned: a non-success is never delivered as a clean acceptance, and an engine status the
        display does not show (an ENTAILED result of a vacuous encoding, a result whose signature or binding the composer
        rejected) is named with the status shown."""
        engine = out.verification.status.value if out.verification is not None else None
        shown = out.display_status.value
        why = (f"the engine returned {engine}, which the outcome does not show" if engine and engine != shown
               else ("no engine result was produced" if engine is None else f"the engine returned {engine}"))
        return IntegrityFinding(code="INT-REQ-006", severity="warning", message=f"claim {claim.claim_id}'s verification gave no verdict: its outcome is displayed {shown} "
                                f"(translation {out.translation.status.value}; {why}), so the router must not read the claim as checked",
                                claim_ids=[claim.claim_id], formal_result_id=out.verification.result_id if out.verification is not None else None, deterministic=False)

    @staticmethod
    def _inconsistent_premises(claim: ClaimRecord, out: ClaimVerificationOutcome) -> IntegrityFinding:
        """INT-REQ-007: the claim's premises contradict each other (engine). An error only for a TRANSLATED claim: when the
        translation is AMBIGUOUS_TRANSLATION, the premises are the translator's assumed reading (a rounded figure encoded
        as an exact equality, say), so the inconsistency belongs to that reading and the specialist is not charged: a
        warning, worded as INT-CONFLICT-005 words a self-refutation under an assumed reading."""
        ids = dict(claim_ids=[claim.claim_id], formal_result_id=out.verification.result_id, deterministic=False)
        if out.translation.status is TranslationStatus.AMBIGUOUS_TRANSLATION:
            interp = out.translation.interpretation
            flags = [f"{a.code}: {a.message[:160]}" for a in (interp.ambiguity_flags if interp is not None else [])][:4]
            why = f" (the translator's ambiguity flags: {flags})" if flags else ""
            return IntegrityFinding(code="INT-REQ-007", severity="warning", message=f"claim {claim.claim_id} rests on premises that contradict each other only under the assumed reading of its AMBIGUOUS_TRANSLATION{why}: the inconsistency belongs to the reading the translator chose (for example a rounded figure encoded as an exact equality), not to the specialist's statement, so the specialist is not charged with an inconsistency", **ids)
        return IntegrityFinding(code="INT-REQ-007", severity="error", message=f"claim {claim.claim_id} rests on premises that contradict each other", **ids)

    def _report_diagnosis(self, report: SpecialistReport, req: Optional[TaskRequest], outcomes) -> "ReportDiagnosis":
        """The report-level argument diagnosis of one delivered report (``translate.diag_core.report_diagnostics``), run once."""
        diagnosis = report_diagnostics(report, self._task_record(req), list(outcomes or []), items=list(req.items) if req is not None else [])
        return ReportDiagnosis(diagnostics=tuple(diagnosis.diagnostics), incomplete=tuple(diagnosis.incomplete))

    @staticmethod
    def _labelled(f):
        """``f`` with the canonical defect label ``named.DEFECT_OF_CODE`` gives its code (a finding that already carries one,
        or whose code names none, is returned unchanged)."""
        if getattr(f, "defect", None) is not None:
            return f
        label = defect_of(f.code, f.message)
        return f.model_copy(update={"defect": label}) if label is not None else f

    @staticmethod
    def _material(d: NamedDiagnostic, materiality: Mapping[str, str], default_claim: Optional[str]) -> bool:
        ids = list(d.claim_ids) or ([default_claim] if default_claim else [])
        if not materiality or not ids:
            return True
        return any(materiality.get(c, "material") == "material" for c in ids)

    def _argument_diagnosis(self, findings: list, structural: list, outcomes, report: Optional[SpecialistReport], report_named) -> tuple[list[NamedDiagnostic], list[IntegrityFinding], dict]:
        """``(the receipt's named diagnostics, the INT-ARG-001 findings, what the summary reports)``: every outcome's
        diagnostics, the report-level ones and one for each labelled finding (``named.from_finding``), ordered and kept within
        ``named.MAX_PER_RECEIPT`` (an overflow is counted, never dropped silently); one INT-ARG-001 for each warning or error
        diagnostic of an outcome or of the report level on a material claim, except where an existing finding already states
        its condition (``CodeSpec.stated_by``). Info never reaches ``findings``."""
        materiality = {c.claim_id: c.materiality for c in report.claims} if report is not None else {}
        named: list[NamedDiagnostic] = []
        arg: list[IntegrityFinding] = []

        def receipt_finding(d: NamedDiagnostic, claim_id: Optional[str], result_id: Optional[str]) -> None:
            spec = NAMED_CODES.get(d.code)
            if d.severity not in ("warning", "error") or (spec is not None and spec.stated_by) or not self._material(d, materiality, claim_id):
                return
            arg.append(IntegrityFinding(code="INT-ARG-001", severity=d.severity, message=finding_message(d), claim_ids=list(d.claim_ids) or ([claim_id] if claim_id else []),
                                        formal_result_id=result_id if d.layer == "engine" else None, related_result_ids=list(d.related_result_ids),
                                        deterministic=True, defect=d.defect))

        for o in outcomes or ():
            rid = o.verification.result_id if o.verification is not None else None
            for d in o.named_diagnostics:
                named.append(d)
                receipt_finding(d, o.claim_id, rid)
        diagnosis = report_named if isinstance(report_named, ReportDiagnosis) else ReportDiagnosis()
        for d in diagnosis.diagnostics:
            named.append(d)
            receipt_finding(d, None, None)
        for f in list(findings) + list(structural):
            if getattr(f, "code", None) == "INT-ARG-001":
                continue
            nd = from_finding(f)
            if nd is not None:
                named.append(nd)
        unique = list({canonical_json(d): d for d in named}.values())
        items = order_named(unique)
        overflow = max(0, len(items) - MAX_PER_RECEIPT)
        return items[:MAX_PER_RECEIPT], arg, self.named_info(outcomes, overflow, list(diagnosis.incomplete)[:64])

    @staticmethod
    def named_info(outcomes, overflow: int = 0, report_incomplete=()) -> dict:
        """What the receipt summary's argument-diagnosis sentence reports beside the counts, from the receipt's structured
        fields alone (``named_overflow``, ``diagnosis_incomplete`` and the outcomes), so a reader can regenerate it."""
        outcomes = list(outcomes or ())
        return {"overflow": int(overflow), "report_incomplete": [str(x) for x in report_incomplete],
                "claims_incomplete": sum(1 for o in outcomes if o.diagnosis_incomplete),
                "engine_undiagnosed": sum(1 for o in outcomes if o.verification is not None and rules_state(o.verification.argument_rules)[0] != "complete")}

    def _encoding_disagreements(self, outcomes, branch_formal, findings) -> list[IntegrityFinding]:
        """INT-XENC-001 (warning): a claim carries both a branch formal check of one of its own statements (the check's
        ``claim_ids`` name it) and a translation the engine decided, and the two definitive answers are opposite: the check
        fails (a clause the claim states does not hold) while the translation's display is a positive verdict (ENTAILED,
        CONSISTENT, SATISFIABLE) on the claim as a whole. At least one of the two encodings misreads the claim, and the
        channel cannot tell which. The converse is no disagreement: a check that holds covers one clause only. Only a
        translation result the composer trusts (a TRANSLATED claim displayed with the engine's own status) and a decided
        check with a signed result are compared; both verdicts stay on the receipt as they are (the check's INT-SUBJ-001 is
        never demoted), and the finding names both result ids. One finding per claim and check pair."""
        if not outcomes or not branch_formal:
            return []
        by_claim: dict[str, list[ClaimVerificationOutcome]] = {}
        for o in outcomes:
            v = o.verification
            if v is None or o.translation.status is not TranslationStatus.TRANSLATED or o.display_status is not v.status:
                continue
            if v.status in _PASSING:
                by_claim.setdefault(o.claim_id, []).append(o)
        have = {(f.formal_result_id, tuple(f.related_result_ids), tuple(f.claim_ids)) for f in findings if f.code == "INT-XENC-001"}
        out: list[IntegrityFinding] = []
        for fc in branch_formal:
            if fc.satisfied is not False or not fc.formal_result_id:
                continue
            for cid in dict.fromkeys(fc.claim_ids):
                for o in by_claim.get(cid, ()):
                    key = (fc.formal_result_id, (o.verification.result_id,), (cid,))
                    if key in have:
                        continue
                    have.add(key)
                    out.append(IntegrityFinding(
                        code="INT-XENC-001", severity="warning",
                        message=(f"two encodings of claim {cid} reach opposite definitive answers: the branch formal check {fc.constraint_id} of the "
                                 f"report's own statement does not hold (engine result {fc.formal_result_id}, {fc.formal_status or 'decided'}), while the "
                                 f"translation's engine result {o.verification.result_id} is {o.verification.status.value} on the claim as a whole. "
                                 f"At least one encoding misreads the claim and the channel cannot tell which: the claim is unresolved, and neither "
                                 f"verdict is withdrawn"),
                        claim_ids=[cid], formal_result_id=fc.formal_result_id, related_result_ids=[o.verification.result_id], deterministic=True))
        return out

    def _finish(self, msg: AgentMessage, direction: str, findings, coverage, constraint_results, outcomes, formal_ids=(), *, structural=(), branch_formal=(), branch_key: Optional[str] = None,
                report: Optional[SpecialistReport] = None, report_named=None) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        structural = [self._labelled(sf) for sf in structural]
        findings = [self._labelled(f) for f in findings]
        try:  # two encodings of one claim that disagree are named; neither verdict is demoted or dropped
            findings = findings + self._encoding_disagreements(outcomes, branch_formal, findings)
        except Exception as exc:  # the comparison only adds; its failure is named, never raised
            findings.append(IntegrityFinding(code="INT-INTERNAL-001", severity="error", message=f"the channel's encoding comparison (INT-XENC-001) check failed internally ({type(exc).__name__}); its findings are missing from this receipt and must not be read as a pass"))
        try:  # the argument diagnosis only adds; its failure is named, never raised
            named, arg_findings, named_info = self._argument_diagnosis(findings, structural, outcomes, report, report_named)
        except Exception as exc:
            named, arg_findings, named_info = [], [IntegrityFinding(code="INT-INTERNAL-001", severity="error", message=f"the channel's argument diagnosis failed internally ({type(exc).__name__}); its findings are missing from this receipt and must not be read as a pass")], {}
        findings = findings + arg_findings
        branch_key = branch_key or self.branch.key
        blocking = _is_blocking(findings)
        subject_flag = any(sf.severity in ("error", "warning") for sf in structural)
        if not blocking:
            self._record_delivery(msg)
        if blocking:
            status = TransmissionStatus.REJECTED
        elif findings or subject_flag or any(o.verification is not None and not is_definitive(o.verification.status) for o in outcomes):
            status = TransmissionStatus.ACCEPTED_WITH_FINDINGS
        else:
            status = TransmissionStatus.ACCEPTED
        ids = list(formal_ids) + [o.verification.result_id for o in outcomes if o.verification is not None] + [f.formal_result_id for f in findings if f.formal_result_id]
        receipt = self._receipt(msg.message_id, direction, status, findings, coverage=coverage, constraint_results=constraint_results, outcomes=outcomes,
                                formal_ids=sorted(set(ids)), structural=structural, branch_formal=branch_formal, branch_key=branch_key, named=named, named_info=named_info,
                                summary=self._summary_response(status, findings, coverage, constraint_results, outcomes, structural, branch_formal, branch_key,
                                                               named=named, named_info=named_info))
        return (msg if status is not TransmissionStatus.REJECTED else None), receipt

    def _receipt(self, message_id: str, direction: str, status: TransmissionStatus, findings, *, coverage=(), constraint_results=(), outcomes=(), formal_ids=(), structural=(), branch_formal=(), summary: str, branch_key: Optional[str] = None,
                 named=(), named_info: Optional[dict] = None) -> TransmissionReceipt:
        r = TransmissionReceipt(receipt_id=uuid.uuid4().hex, message_id=message_id, request_id=self.plan.request_id, task_id=self.plan.task_id, direction=direction,
                                status=status, findings=list(findings), coverage=list(coverage), constraint_results=list(constraint_results), outcomes=list(outcomes),
                                branch=branch_key or self.branch.key, structural_findings=list(structural), formal_checks=list(branch_formal),
                                formal_result_ids=list(formal_ids), summary=_fit_summary(summary), created_at=_now(), named_diagnostics=list(named),
                                named_overflow=int((named_info or {}).get("overflow", 0)), diagnosis_incomplete=list((named_info or {}).get("report_incomplete", [])))
        self.receipts.append(r)
        return r

    @staticmethod
    def _summary_request(req: TaskRequest, findings, status) -> str:
        return (f"Request {status.value}: {len(req.items)} item(s) extracted, {len(req.constraints)} constraint(s) ({', '.join(c.kind for c in req.constraints) or 'none'}), "
                f"{len(req.supplied_texts)} supplied text(s); findings: {', '.join(sorted({f.code for f in findings})) or 'none'}.")

    @staticmethod
    def _argument_summary(named, named_info: Optional[dict]) -> str:
        """The receipt summary's argument-diagnosis sentence: counts by shown severity, then what was capped, what overflowed
        and what was not computed or did not finish (never read as "none found")."""
        counts = summary_counts(list(named))
        text = (f"Argument diagnosis: {counts['named']} named on {counts['claims']} claim(s) ({counts['warning_or_error']} warning or error, "
                f"{counts['info']} info; rules {ARG_RULES_VERSION})")
        info = named_info or {}
        extra = []
        if counts["capped"]:
            extra.append(f"{counts['capped']} capped, still blocking release")
        if info.get("overflow"):
            extra.append(f"{info['overflow']} more beyond the receipt bound of {MAX_PER_RECEIPT}, not listed")
        if info.get("engine_undiagnosed"):
            extra.append(f"engine diagnosis not computed or incomplete for {info['engine_undiagnosed']} result(s)")
        if info.get("claims_incomplete"):
            extra.append(f"incomplete on {info['claims_incomplete']} claim(s)")
        if info.get("report_incomplete"):
            extra.append("report rules incomplete: " + ", ".join(str(x)[:80] for x in info["report_incomplete"][:3]))
        return text + ("; " + "; ".join(extra) if extra else "") + ". "

    @staticmethod
    def _summary_response(status, findings, coverage, constraint_results, outcomes, structural=(), branch_formal=(), branch="generic", *, named=(), named_info=None) -> str:
        covered = sum(1 for c in coverage if c.addressed)
        verdicts = {}
        for o in outcomes:
            verdicts[o.display_status.value] = verdicts.get(o.display_status.value, 0) + 1
        # The report's own formal checks are summarised as counts (a long report yields one per arithmetic or dated
        # sentence); only the checks that did not hold are named, and at most a few.
        failed = [c.constraint_id for c in branch_formal if c.satisfied is False]
        undecided = [c.constraint_id for c in branch_formal if c.satisfied is None]
        ok = len(branch_formal) - len(failed) - len(undecided)
        bf = f"{len(branch_formal)} ({ok} ok, {len(failed)} FAILED, {len(undecided)} undecided)" if branch_formal else "none"
        if failed:
            bf += f"; FAILED: {_named(failed)}"
        if undecided:
            bf += f"; undecided: {_named(undecided)}"
        histogram: dict[str, int] = {}
        for sf in structural:
            histogram[sf.code] = histogram.get(sf.code, 0) + 1
        subject = ", ".join(f"{code} x{n}" for code, n in sorted(histogram.items())) or "none"
        return (f"Transmission {status.value} via branch {branch}. Items addressed (heuristic): {covered}/{len(coverage)}. Request constraints: "
                + (", ".join(f"{c.constraint_id}={'ok' if c.satisfied else 'FAILED' if c.satisfied is False else 'unchecked'}" for c in constraint_results) or "none")
                + f". Report's own formal checks: {bf}. Subject findings: {subject}. Claim outcomes: {verdicts or 'none'}. "
                f"Findings: {', '.join(sorted({f.code for f in findings})) or 'none'}. " + TranslatorChannel._argument_summary(named, named_info) + _SCOPE_TAIL)
