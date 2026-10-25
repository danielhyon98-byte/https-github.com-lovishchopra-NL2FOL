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
agents are named, not reconciled. A relay or forward of a report carries its history: the
receipt references every earlier delivered transmission of the same report on this channel
(its arrival from the specialist first) with what each left unresolved, and carries each
unresolved finding forward as INT-HIST-001 with its own severity, so a later transmission
that re-checks less (a relay runs without the request; a forward re-checks nothing) never
erases an earlier failed Given check or warning; a synthesis carries the history of the
reports it cites, for the claims it cites. A synthesis is checked for undisclosed contradictions
between the claims it accounts for (INT-CONFLICT-002), for figures and dates (in digits or
words, with their scale words) that occur in none of its sources or are re-paired between
events, for quotations no supplied text or cited report holds (INT-LEDGER-025), for a
reversed direction or a dropped negation (INT-LEDGER-026), and, when a synthesized claim
carries (or can be given) a formal conclusion, for entailment by its formalized sources;
when that cannot be checked, the receipt says so instead of implying a check that nobody
ran (INT-LEDGER-011, INT-SYNTH-012). Raw text that is not valid Unicode (a lone UTF-16
surrogate) is refused before parsing (INT-REQ-009); nothing raises into the router.

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

Argument diagnosis (rules ``argdiag-2``, ``named``): the branch formal checks and the constraint-bound
checks are code-built checks, not specialist arguments, so they run with ``diagnose=False``. Every
receipt carries ``named_diagnostics``: each outcome's diagnostics, the report-level diagnostics
(``translate.diag_core.report_diagnostics``, run once per delivered report) and a named diagnostic for
each structural or integrity finding that carries a ``defect`` (the channel labels existing codes through
``named.DEFECT_OF_CODE`` when it builds the receipt; INT-SUBJ-001 and INT-SUBJ-004 take the
FormalCheck's own ``defect`` first, else its kind's label). Each warning or error diagnostic of an outcome
or of the report level on a material claim is also one INT-ARG-001 finding carrying its ``defect``
(ARG-CONTRA-001 excepted: INT-REQ-007 already states it); info diagnostics never reach ``findings``, so
they never change the receipt status. The summary counts them ("Argument diagnosis: N named on K claims
...") before the scope tail.
"""
from __future__ import annotations

import inspect
import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping, Optional, Union, get_args

from pydantic import BaseModel, ValidationError

from ..engine.errors import DiagnosticCode
from ..engine.policies import UnknownPolicyError, policy_config, policy_limits
from ..engine.results import SolverConfig, VerificationResult
from ..engine.runner import verify
from ..engine.statuses import VerificationStatus as S, is_definitive
from ..integrity.contracts import (AgentMessage, AgentRole, ConflictRecord, IntegrityFinding, LedgerEntry, SYNTHESIZED_CLAIM_TRANSFORMATIONS, Synthesis,
                                   SynthesizedClaim, WorkPlan, payload_hash)
from ..integrity.cross_check import check_conflict_disclosure, check_cross_report_consistency, check_paraphrase_coverage, check_synthesis_entailment
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
from ..version import ARG_RULES_VERSION
from ..translate.grounding import check_claim_sources, locate_long_elision, locate_quotation, locate_quotation_inexact
from .contracts import (Constraint, ConstraintResult, CoverageRecord, ReceiptReference, SUMMARY_MAX_CHARS, TaskRequest, TransmissionReceipt, TransmissionStatus,
                        carried_finding, carried_subject_finding)
from .cues import (FINDING_CODE_PATTERN, FORMAT_PHRASES, FORMAT_VERBS, FORMAT_WORDS, FUNCTION_WORDS, SYSTEM_CHECK_PHRASES, VERDICT_CUES,
                   phrase_regex, verdict_cue_regex)
from .request_parser import (
    LEVEL3_VERDICT_TERMS,
    MAX_CONSTRAINTS,
    MAX_ITEMS,
    count_answer_words,
    count_paragraphs,
    deliverable_blocks,
    extract_constraints,
    extract_constraints_counted,
    extract_items,
    extract_items_counted,
    measure_answer_words,
    part_label,
    part_section_text,
)

#: The injected claim verifier: ``fn(claim, report)``. A verifier that also declares a ``task`` parameter (or ``**kwargs``)
#: is called ``fn(claim, report, task=<TaskRecord>)`` with the task record of the request the report answers (the router's
#: request text, an application-created record: ``translate.contracts.TaskRecord``), so a premise that claims the task's
#: authority can be validated against the task's own wording and a fidelity reviewer is shown the original task.
VerifyClaimFn = Callable[..., Optional[ClaimVerificationOutcome]]


@dataclass(frozen=True)
class ReportDiagnosis:
    """The report-level argument diagnosis of one delivered report: what it named and the rules that did not finish."""
    diagnostics: tuple[NamedDiagnostic, ...] = ()
    incomplete: tuple[str, ...] = ()


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
#: tail claim; the channel turns it into a finding naming how much went unchecked (INT-REQ-013).
_FOLDED_TAIL_RE = re.compile(r"(?P<n>\d+) (?:claims|sentences) beyond the report's claim limit \((?P<limit>\d+)\) were merged into claim (?P<tail>\S+)")
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
_SUMMARY_TRUNCATED = " ...[summary truncated] "
_MAX_NAMED = 8
#: Contract lengths of a ConstraintResult detail and of a finding message.
_DETAIL_MAX = 2000
_VACUOUS = DiagnosticCode.VACUOUS_RESULT.value
#: Wall-clock budget for the STEM checks of one report (kinds ``stem_*``): checks left when it is spent are undecided
#: (INT-SUBJ-002, "check budget"), never success. Other packs' checks are not budgeted.
STEM_CHECK_BUDGET_S = 8.0
#: A UTF-16 surrogate code point. In a Python string every one is unpaired as far as Unicode is concerned (a truncated
#: emoji arriving in an agent's JSON as "\\ud83d"): it has no UTF-8 form and no contract accepts it, so text carrying one
#: is rejected at the channel boundary (INT-REQ-009) before it is parsed or hashed.
_SURROGATE_RE = re.compile("[\ud800-\udfff]")
#: The code of a finding carried from an earlier receipt (relay history): its severity is the original finding's.
_HISTORY_CODE = "INT-HIST-001"
#: The subject findings about a report's paragraphs and sentence style (the English and History essay rules: a body
#: paragraph's quotations, judgement move or dated items, a sentence that is only a quotation, the essay's length): a
#: synthesis, which restates claims and not paragraphs, does not carry them (close round 2, DIFF-05); a relay or a
#: forward of the report itself still does.
_LAYOUT_PREFIXES: tuple[str, ...] = ("ES-STR-", "ES-STY-", "HI-STR-")
#: The warnings that state a fault the content itself was found to have (accuracy round 1, DV2-05): a branch check that
#: failed under a reading the report did not state (INT-SUBJ-004, with its signed result), a named defect of a claim's
#: argument (INT-ARG-001) and a system check result handed to the reader as subject content (INT-REQ-017). A forward of a
#: report to a peer specialist and a synthesis carry an earlier receipt's errors and these warnings only: a heuristic
#: reading (coverage, layout, a word or paragraph bound of the original request, a derived figure not decided, a quotation
#: that could not be verified, a relation outside the encodings, a parse note, a conflict under an assumed reading that
#: charges no one, one symbol glossed two ways) is no fault of the material the recipient builds on, so it stays listed in
#: the history the receipt references and is not carried.
_DECIDED_WARNINGS: frozenset[str] = frozenset({"INT-SUBJ-004", "INT-ARG-001", "INT-REQ-017"})
#: The subject findings at warning such a transmission carries too: the STEM defects (the STEM rows of the named-code table,
#: ``named.NAMED_CODES``: a wrong formula, a missing conversion, an invalid step, a rounding that changes the conclusion, an
#: extrapolation, missing working, contradictory givens, a symbol conflict; and the dimension and symbol checks that state a
#: dimension error or one symbol for two quantities, ST-DIM-001, ST-DIM-002, ST-SCOPE-001), each a deterministic reading of
#: a fault the content was found to have; a parse note, an undecided relation or another heuristic subject reading is not
#: carried.
_DECIDED_SUBJECT_WARNINGS: frozenset[str] = frozenset({code for code, spec in NAMED_CODES.items() if spec.layer == "stem"}
                                                      | {"ST-DIM-001", "ST-DIM-002", "ST-SCOPE-001"})
#: Most earlier receipts one receipt references (the first, a report's arrival, is always kept) and most findings it
#: carries from them (the last one then says how many more the history lists).
_MAX_HISTORY = 32
_MAX_CARRIED = 64


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
        if len(w) > 4 and w.endswith("ies"):  # "burglaries" meets "burglary", "studies" meets "study" (B18)
            w = w[:-3] + "y"
        out.add(light_stem(w))
    return out


#: Words of an item that say THAT something is to be calculated or how to give it, not WHAT: the command words of a
#: calculation ("calculate", "find", "determine", "solve", "show", "convert", "evaluate"), the words that name the output of
#: any calculation ("value", "answer", "result", "number", "expression", "equation", "solution") and the instructions on its
#: form and its givens ("exact", "significant figures", "decimal places", "nearest", "without a calculator", "given",
#: "using", "working"). A claim that shares only these with an item addresses it only when the item names nothing else;
#: an item that names what it wants ("the acceleration", "the gradient", "the pH") is addressed only by a claim about that,
#: through its own words or the words its branch lends it (a STEM claim's quantities, units and symbols), never by an
#: imperative alone (STEM review S3).
_COMMAND_STEMS = frozenset(light_stem(w) for w in (
    "calculate calculation calculations compute computation determine find work out solve deduce derive estimate evaluate verify show prove "
    "convert simplify expand factorise factorize rearrange balance state give write down obtain use hence copy complete express "
    "value values answer answers result results number numbers expression expressions equation equations solution solutions "
    "exact exactly form significant figure figures decimal place places nearest correct accurate accuracy round rounded calculator "
    "without given giving using working workings method full each your final appropriate suitable").split())
#: Words that are no evidence that a claim is about the request's topic when the single-item rule (B18) reads the request
#: as a whole: function words, the words of the answer's form and its command verbs (the cue tables of the format
#: instructions), the frame nouns of an ask ("Evaluate the CLAIM that ...", "the statement that ...") and a few more
#: function words. A quotation that shares only "one" with "Write one analytical paragraph ..." or an off-subject answer that
#: shares only "claim" with "Evaluate the claim that ..." addresses nothing.
_NOT_TOPIC_STEMS = frozenset(light_stem(w) for w in (
    list(FUNCTION_WORDS) + list(FORMAT_WORDS) + list(FORMAT_VERBS) + [w for p in FORMAT_PHRASES for w in p.split()]
    + "has have had than about between within without into onto over under after before during which who whom whose why when where "
      "claim claims statement statements question questions view views idea ideas point points".split()))
#: The label a request gives an item before its text ("Guiding question:", "Essay question:", "Question 2:"): not a term
#: the answer must repeat.
_ITEM_LABEL_RE = re.compile(r"^\s*(?:guiding|essay|research|prescribed|key|focus)?\s*(?:question|title|prompt|task)(?:\s+\d+)?\s*:\s*", re.IGNORECASE)
#: Written arithmetic: a figure, an operator, a figure, then '=' ('$5.00 − $3.00 =', '40,000 ÷ 2.00 =', '0.5 × 2.0 × 3.0² =').
_ARITHMETIC_LINK_RE = re.compile(r"[$£€]?\d[\d,.]{0,20}\s{0,3}[−+×÷*/·-]\s{0,3}[$£€(]?\d[\d,.²³]{0,20}[^=\n]{0,40}?=")


def _worked_calculations(response: str) -> int:
    """How many worked calculations (an operand, an operator, an operand and a result sign: :data:`_ARITHMETIC_LINK_RE`) the
    response writes outside quotation marks. Bounded: the first 64 of the first 400,000 characters."""
    from ..adapters.markdown import mask_quotations
    body = mask_quotations((response or "")[:400_000])
    return sum(1 for _k, _m in zip(range(64), _ARITHMETIC_LINK_RE.finditer(body)))


def _writes_own_arithmetic(response: str, request: str) -> bool:
    """True when the response writes arithmetic the request does not ('$5.00 − $3.00 = $2.00' for a request that gives the two
    prices): a computation, which no restatement of the request is. Bounded: the first 64 links of the first 400,000
    characters, each looked up in the request with its whitespace collapsed."""
    ask = " ".join((request or "")[:400_000].split())
    for k, m in enumerate(_ARITHMETIC_LINK_RE.finditer(response[:400_000])):
        if k >= 64:
            break
        if " ".join(m.group(0).split()) not in ask:
            return True
    return False


#: A mark annotation of a request item ("[2 marks]", "[3]", "[2 + 2]", "(4 marks)"): the item's furniture, never a topic term.
#: (security round 1) Every quantifier of the bracket forms possessive: each is followed by a token its own characters cannot
#: begin (digits by a space, a plus, 'marks' or the closing bracket; a space by a digit, a plus, 'marks' or the bracket), so its
#: longest reading is the only one the rest can follow and the same annotations are read. The spaces after '[1' were split
#: between two or three quantifiers before failing (quadratic in the run) (tests/channel/test_security_round1_marks.py).
_MARK_ANNOTATION_RE = re.compile(r"\[\s*+\d{1,3}+(?:\s*+\+\s*+\d{1,3}+){0,4}+\s*+(?:marks?+)?+\s*+\]|\(\s*+\d{1,3}+\s*+marks?+\s*+\)", re.IGNORECASE)
#: Markup an answer may wrap its part labels in ("**Part (a) — find**", "$x$").
_MARKUP_CHARS_RE = re.compile(r"[*_`$#]")
#: A claim that is a row of a table ("| 0 | 1 | 1 |"): it offers the coverage heuristic the word "table".
_TABLE_CLAIM_RE = re.compile(r"^\s*\|[^\n]*\|\s*$")


def _answer_sections(text: str) -> list[tuple[int, frozenset[str]]]:
    """``(offset, labels)`` for every line of the answer (markup removed) that opens with a part label: "(a)", "Part
    (b) —", "1.", and a nested "3. a)", "(a)(i)" or "1(a)" (labels 3 and a; a and i; 1 and a). Offsets are in the
    markup-free text."""
    from .request_parser import part_label
    plain = _MARKUP_CHARS_RE.sub("", text)
    out: list[tuple[int, frozenset[str]]] = []
    pos = 0
    for line in plain.split("\n"):
        lab = part_label(line)
        if lab is not None:
            labels = {lab}
            rest = re.sub(r"^\W{0,4}(?:part\s+)?(?:\(?[0-9a-z]{1,4}[.)]\)?|\d{1,2}(?=\())\s*", "", line.strip(), flags=re.IGNORECASE)
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


#: Displays that say a claim's check produced no verdict on it although it was eligible and put to the translation: an
#: encoding that is no verdict (vacuous E108, E110-E112, an invalid formalization), a result the composer did not trust
#: (signature, binding, staleness), a translation that failed, a claim the translation read as ambiguous (the chosen
#: reading's engine status is never its verdict) and a claim the encoding cannot express (UNSUPPORTED) (repair round 1,
#: re-run review correctness-2 variant). A NOT_ELIGIBLE claim is outside what was asked of the engine and is reported by
#: its display alone.
_NO_RESULT_DISPLAYS = frozenset({S.INVALID_FORMALIZATION, S.INTERNAL_ERROR, S.AMBIGUOUS_TRANSLATION, S.UNSUPPORTED})


def _no_result(o: ClaimVerificationOutcome) -> bool:
    """True when ``o`` holds no verdict that a clean receipt could stand on (correctness-2): the engine gave a non-result
    (TIMEOUT, UNKNOWN, ...), or the outcome is displayed INVALID_FORMALIZATION, INTERNAL_ERROR, AMBIGUOUS_TRANSLATION or
    UNSUPPORTED (:data:`_NO_RESULT_DISPLAYS`), or the composer displays something other than the engine's definitive status
    for a TRANSLATED claim (it refused that result). The receipt is then ACCEPTED_WITH_FINDINGS, never ACCEPTED; the claim's
    display already says why."""
    if o.display_status in _NO_RESULT_DISPLAYS:
        return True
    if o.verification is None:
        return False
    if not is_definitive(o.verification.status):
        return True
    return o.translation.status is TranslationStatus.TRANSLATED and o.display_status is not o.verification.status


#: B20: the translation displays that are a positive verdict on a claim as a whole.
_PASSING = frozenset({S.ENTAILED, S.CONSISTENT, S.SATISFIABLE})


#: A response read as an answer wrapped in JSON is at most this long, and its JSON is read to at most this many string values.
_WRAPPED_MAX_CHARS = 400_000
_WRAPPED_MAX_STRINGS = 256


def _wrapped_answer_words(report: SpecialistReport, material: list, view=None) -> int:
    """The answer words of a response that is one JSON object wrapping the answer (``{"answer": "The 1929 crash ..."}``, a
    mapping report whose original response is the provider's raw JSON): the words of the object's string values that hold a
    material claim's text, counted as any answer's are (repair round 2, robustness-and-contracts-7). 0 when the response is
    not one JSON object or no string value holds a material claim (a pasted receipt stays meta-text). The JSON is read as
    data by the standard parser; nothing in it is executed."""
    text = (report.original_response or "").strip()
    if not (text.startswith("{") and text.endswith("}")) or len(text) > _WRAPPED_MAX_CHARS:
        return 0
    try:
        obj = json.loads(text)
    except (ValueError, RecursionError):
        return 0
    strings: list[str] = []
    stack = [obj]
    while stack and len(strings) < _WRAPPED_MAX_STRINGS:
        node = stack.pop()
        if isinstance(node, str):
            strings.append(node)
        elif isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    # a claim's own text in a string value (a claim that is itself JSON, or a fragment of a few characters, holds nothing)
    claims = [ct for c in material if len(ct := (c.claim_text or "").strip()) >= 8 and not ct.startswith(("{", "["))]
    held = [x for x in strings if any(ct in x for ct in claims)]
    if not held:
        return 0
    return count_answer_words("\n\n".join(held), view=view)[0]


def _asks_nothing(text: str) -> bool:
    """No character of ``text`` is visible: whitespace, control characters and format characters only (zero-width spaces and
    joiners, a byte-order mark: Unicode categories Cc and Cf). Such a request asks nothing (repair round 2, empty-request
    residual: '\u200b\u200c\u200d' and '\x00\x01' were dispatched)."""
    import unicodedata
    for ch in text:
        if ch.isspace() or unicodedata.category(ch) in ("Cc", "Cf"):
            continue
        return False
    return True


def _shape_reason(exc: BaseException, contract: str = "report") -> str:
    """Describe why parsing or validation failed without echoing the agent's text. A field error names its location and
    its type only; an error of the contract as a whole (a model validator, which has no location) names the ``contract``
    and the validator's own fixed message ("synthesis: text_sha256 does not match text", "synthesis: duplicate
    synthesized claim_id"), cut to 160 characters: those messages are written by this code, never by the agent."""
    if isinstance(exc, ValidationError):
        parts = []
        for e in exc.errors()[:6]:
            loc = ".".join(str(x) for x in e.get("loc", ()))
            kind = e.get("type", "invalid")
            if kind == "value_error":
                # a validator's own fixed message, of the contract as a whole or of one field ("conflicts.0: a conflict needs
                # two parties", "created_at: ..."; repair round 2, combinator-faults-11), with the field's value never shown
                msg = _scrub(str(e.get("msg", "")))
                msg = msg[len("Value error, "):] if msg.startswith("Value error, ") else msg
                given = e.get("input")
                if isinstance(given, (str, int, float)) and len(str(given)) >= 1 and str(given) in msg:
                    msg = msg.replace(str(given), "<the given value>")
                parts.append(f"{loc or contract}: {msg[:160]}" if msg else f"{loc or contract}: value_error")
            else:
                parts.append(f"{loc or contract}: {kind}")
        more = len(exc.errors()) - 6
        return "; ".join(parts) + (f"; +{more} more" if more > 0 else "")
    return str(exc)[:300]


#: Longest identifier an envelope or a finding carries (the contracts' bound on message, agent and report ids).
_ID_MAX = 128


def _valid_id(value) -> Optional[str]:
    """``value`` when it is an identifier the contracts can carry (a string of 1 to 128 characters with no lone surrogate),
    else None: a message id, agent id or report id handed to the channel in any other form (None, a number, a list, an
    over-long string) is refused as an unreadable identifier, never raised (E2E robustness findings)."""
    if isinstance(value, str) and 1 <= len(value) <= _ID_MAX and not _SURROGATE_RE.search(value):
        return value
    return None


def _shown_id(value) -> str:
    """An identifier as a finding may name it: its text with surrogates replaced, cut to 128 characters (a non-string is
    named by its type)."""
    if isinstance(value, str):
        return _scrub(value)[:_ID_MAX]
    return f"<{type(value).__name__}>"


def _role_of(value) -> Optional[AgentRole]:
    """``value`` as an ``AgentRole`` (a role given as its string value is the same role), or None when it is none."""
    if isinstance(value, AgentRole):
        return value
    if isinstance(value, str):
        try:
            return AgentRole(value)
        except ValueError:
            return None
    return None


#: A response handed over as raw text that opens like a JSON object ('{"', or a list of them), possibly in a code fence:
#: a report sent as JSON, which is read as JSON (a whole report goes through the report path; a truncated or malformed
#: one is refused), never as prose.
_JSON_OPEN_RE = re.compile(r"^(?:\{\s*\"|\[\s*\{\s*\")")
#: Keys that make a JSON object a report payload rather than prose data pasted as an answer.
_REPORT_KEYS = ("report_id", "claims", "original_response", "response_sha256")


#: The keys of a JSON object that only carries the answer ('{"answer": "..."}'): its one string value is the response text
#: (repair round 1, re-run review rc-7 residual). Any other key, or a second key, makes it no envelope.
_ANSWER_ENVELOPE_KEYS = frozenset({"answer", "response", "text", "content", "output", "reply", "message", "body"})


def _answer_in_envelope(text: str) -> Optional[str]:
    """The answer of a response delivered as a JSON object whose one key is an answer key (:data:`_ANSWER_ENVELOPE_KEYS`:
    '{"answer": "..."}'), read with the JSON decoder (data, never evaluated); None for any other text, and for an envelope
    that holds no text. A response that is one string in double quotes ('"The crash of 1929 ..."') is no envelope: it is
    also a whole-answer quotation, and reading it as the words inside would take its quotation marks, and every quotation
    check on them, away (a misquotation of a supplied text written as the whole answer would no longer be checked)."""
    s = text.strip()
    if len(s) < 2 or s[0] != "{":
        return _answer_in_tag(s)
    try:
        obj = json.loads(s)
    except (ValueError, RecursionError):
        return None
    # envelopes nested in envelopes ('{"response": {"text": "..."}}'): each level one answer key, at most four levels (repair
    # round 5, rerun-robustness-and-contracts-7 variant: a nested envelope was read as one claim of JSON text, "no answer")
    for _level in range(4):
        if not (isinstance(obj, Mapping) and len(obj) == 1):
            return None
        ((key, value),) = obj.items()
        if not (isinstance(key, str) and key.casefold() in _ANSWER_ENVELOPE_KEYS):
            return None
        if isinstance(value, str):
            inner = value.strip()
            return inner or None
        obj = value
    return None


#: An answer delivered between one pair of envelope tags ('<answer>...</answer>', any answer key as the tag name).
_ANSWER_TAG_RE = re.compile(r"<(?P<tag>" + "|".join(sorted(_ANSWER_ENVELOPE_KEYS)) + r")>(?P<body>.*)</(?P=tag)>", re.IGNORECASE | re.DOTALL)


def _answer_in_tag(s: str) -> Optional[str]:
    """The answer of a response that is one envelope tag around its text ('<answer>The crash ...</answer>'); None otherwise
    (a tag inside the text, two tags, or none)."""
    if not s.startswith("<") or len(s) > 400_000:
        return None
    m = _ANSWER_TAG_RE.fullmatch(s)
    if m is None or "<" + m.group("tag").casefold() in m.group("body").casefold():
        return None
    inner = m.group("body").strip()
    return inner or None


#: A structured reply's opening: a Python-notation envelope or report ("{'answer': ...", its key an answer or report key, so
#: a dictionary a Computer Science answer writes is no reply), an envelope tag ('<answer>') or, on a line of its own after
#: prose, a JSON report ('{"report_id": ...').
_PY_OBJECT_OPEN_RE = re.compile(r"^\{\s*'(?:" + "|".join(sorted(_ANSWER_ENVELOPE_KEYS) + list(_REPORT_KEYS)) + r")'\s*:", re.IGNORECASE)
_TAG_OPEN_RE = re.compile(r"^<(?P<tag>" + "|".join(sorted(_ANSWER_ENVELOPE_KEYS)) + r")>", re.IGNORECASE)
_EMBEDDED_REPORT_RE = re.compile(r"(?m)^[ \t]*\{\s*\"(?:" + "|".join(_REPORT_KEYS) + r")\"\s*:")


def _unclosed(body: str) -> bool:
    """Whether an object written as text ends inside a string or with a bracket left open: one linear scan of quotes
    (single and double, backslash escapes) and brackets."""
    depth = 0
    quote = ""
    escaped = False
    for ch in body:
        if quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
    return bool(quote) or depth > 0


def _cut_structured_reply(text: str) -> Optional[str]:
    """Why a response is a structured reply that never closes, cut off in transit, or a JSON report embedded after prose
    (repair round 5, rerun-robustness-and-contracts-8 variant): a Python-notation object left unclosed ("{'answer': 'The
    crash came in 1929 after"), an envelope tag with no closing tag ('<answer>... Banks fa'), or a line of prose followed by
    a JSON report object ('Intro text.\n{"report_id": ...'). None for any other text (prose, a complete reply). Nothing in
    the reply is evaluated: the reading is a scan of its characters."""
    s = text.strip()
    if len(s) > 400_000:
        return None
    if _PY_OBJECT_OPEN_RE.match(s) and _unclosed(s):
        return f"an object in Python notation cut off at character {len(s):,} (unclosed quotes or brackets: truncated in transit)"
    m = _TAG_OPEN_RE.match(s)
    if m is not None and re.search(rf"</{re.escape(m.group('tag'))}>", s, re.IGNORECASE) is None:
        return f"an envelope tag '<{m.group('tag')}>' with no closing tag, cut off at character {len(s):,} (truncated in transit)"
    e = _EMBEDDED_REPORT_RE.search(s)
    head = s[e.start():e.start() + 400] if e is not None else ""
    # a report, not a JSON example in an answer: its id key, or two of the report's keys, open it
    if e is not None and e.start() > 0 and s[:e.start()].strip() and (
            '"report_id"' in head or sum(f'"{k}"' in head for k in _REPORT_KEYS) >= 2):
        rest = s[e.start():].strip()
        try:
            json.loads(rest)
            how = "a complete JSON report"
        except (ValueError, RecursionError) as exc:
            how = "a JSON report cut off in transit" if (isinstance(exc, json.JSONDecodeError) and (exc.msg.startswith("Unterminated") or exc.pos >= len(rest) - 1)) else "malformed JSON"
        return f"{how} at character {e.start():,}, after {e.start():,} character(s) of prose: a report is sent as JSON alone"
    return None


def _json_text(text: str) -> Optional[str]:
    """The JSON body of ``text`` when the response is a JSON object written as text (its stripped text, or the body of the
    one code fence it consists of, opens with '{"' or '[{"'); None for any other text."""
    s = text.strip()
    if s.startswith("```"):
        nl = s.find("\n")
        if nl < 0:
            return None
        body = s[nl + 1:].rstrip()
        if body.endswith("```"):
            body = body[:-3].rstrip()
        s = body.strip()
    return s if _JSON_OPEN_RE.match(s) else None


#: INT-REQ-017: a system check result written into an answer as content (closed phrases, matched in any case, or a finding
#: code, matched as written).
_SYSTEM_CHECK_RE = re.compile(r"\b(?:" + phrase_regex(SYSTEM_CHECK_PHRASES) + r")\b", re.IGNORECASE)
_FINDING_CODE_RE = re.compile(FINDING_CODE_PATTERN)


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


def _dedupe_ids(ids) -> list[str]:
    return list(dict.fromkeys(ids))


def _located(excerpt: str, text: str, document_id: Optional[str] = None) -> bool:
    """The quoted words occur in ``text`` in some form (exact, normalized, elided, a form difference or a long elision).
    ``document_id`` names a supplied text for the grounding cache; the answer never depends on it."""
    return bool(excerpt.strip()) and (locate_quotation(excerpt, text, document_id=document_id) is not None
                                      or locate_quotation_inexact(excerpt, text, document_id=document_id) is not None
                                      or locate_long_elision(excerpt, text, document_id=document_id) is not None)


#: A premise label of a report's own check: "before = 1,500 in 1840" (the figure as stated), "January 1923" (a dated event).
_PREMISE_VALUE_RE = re.compile(r"^(?:[\w ]{1,40}?=\s*)?(?P<v>.+?)(?:\s*\(stated in sentence \d+ of the paragraph\))?$")
_FIRST_FIGURE_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


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
_FIGURE_SCALE_RE = re.compile(r"[$£€¥]?\d[\d,]*(?:\.\d+)?(?:\s+(?:thousand|million|billion|trillion))?")
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
    found = [x for x in (_find_anchor(low, _PERIOD_EDGE_RE.sub("", a)) for a in anchors if a) if x[0] >= 0]
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
        m = _PREMISE_VALUE_RE.match((pr.label or "").strip())
        if m and m.group("v").strip():
            anchors.append(m.group("v").strip())
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


def _strict_contract(model, data: Mapping):
    """``model`` validated from ``data``, a mapping received as JSON, strictly, as the IR and the service's report route
    are: "yes" is no boolean and "1" no integer. The mapping is written as JSON text first, so strings stay valid where the
    contract reads them from JSON (enumerations, timestamps); a value JSON cannot hold (not serialisable, NaN) or a lone
    surrogate (no Unicode text) is refused like any other invalid value (``ValueError`` or ``ValidationError``)."""
    try:
        text = json.dumps(data, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError(f"the mapping is not JSON data ({type(exc).__name__})") from None
    return model.model_validate_json(text, strict=True)


def _coerce_payload(payload) -> tuple[Optional[Union[SpecialistReport, Synthesis]], str, list[IntegrityFinding]]:
    """A relayed payload that is not a contract model: a mapping is validated against the contract its shape names
    (``synthesis_id``: a synthesis; ``report_id``: a specialist report). ``(model, "", [])``, or ``(None, why, named)``:
    ``named`` holds INT-SYNTH-014 when a synthesis fails on a value outside a closed vocabulary (``_vocabulary_findings``)."""
    if isinstance(payload, Mapping):
        data = dict(payload)
        model = Synthesis if "synthesis_id" in data else SpecialistReport if "report_id" in data else None
        if model is None:
            return None, "a mapping that names neither a report_id nor a synthesis_id", []
        name = "synthesis" if model is Synthesis else "specialist_report"
        try:
            return _strict_contract(model, data), "", []
        except (ValidationError, TypeError, ValueError) as exc:
            named = _vocabulary_findings(data, exc) if model is Synthesis and isinstance(exc, ValidationError) else []
            return None, f"a mapping that does not validate against the {name} contract: {_shape_reason(exc, name)}", named
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

    def __init__(self, plan: WorkPlan, *, signing_key: bytes, key_id: str = "channel",
                 verify_claim_fn: Optional[VerifyClaimFn] = None, config: SolverConfig = SolverConfig(), registry=None,
                 formalize_synthesis_fn: Optional[FormalizeSynthesisFn] = None) -> None:
        if not signing_key:
            raise ValueError("a signing key is required")
        if registry is None:
            from ..branches import default_registry
            registry = default_registry()
        self.registry = registry
        self.branch, self.profile = registry.for_subject(plan.subject)
        # An agent the plan assigns another subject (a History specialist consulted on a Literature task) is served by
        # that subject's branch: its requests carry that subject, its raw text is parsed by that branch's adapter and its
        # reports run through that branch's packs. Everything else on the channel (ledger, pool, hand-off) is shared.
        self._agent_branches = {aid: registry.for_subject(subj) for aid, subj in plan.agent_subjects.items()}
        self.plan = plan
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
        self.superseded: dict[str, str] = {}                 # report_id -> report id that superseded it (INT-HANDOFF-009)
        self.conflicts_seen: list[tuple[frozenset[str], Optional[str]]] = []  # INT-CONFLICT-001 claim sets named on this channel
        self.receipts: list[TransmissionReceipt] = []
        self._seen_payloads: dict[str, str] = {}             # payload hash|recipient -> first message id DELIVERED with it
        self.report_recipients: dict[str, set[str]] = {}     # report_id -> recipients (role|agent) it was delivered to
        self.syntheses: dict[str, Synthesis] = {}            # synthesis_id -> the FIRST synthesis delivered under that id; never overwritten
        self.synthesis_recipients: dict[str, set[str]] = {}  # synthesis_id -> recipients (role|agent) it was delivered to
        self.router_ids: set[str] = set()                    # agent ids that sent this channel's accepted requests: the router's identity
        self.payload_history: dict[tuple[str, str], list[str]] = {}  # ("report"|"synthesis", id) -> receipt ids of its delivered transmissions, in order
        self._receipt_index: dict[str, TransmissionReceipt] = {}     # receipt id -> receipt
        self.delivered_to_router: dict[str, list[str]] = {}  # report_id -> message ids under which it was delivered to the router
        self.forward_of: dict[str, str] = {}                 # forward message id -> the delivery message id it carries on

    def _branch_for(self, agent_id: Optional[str]):
        """(branch, profile) serving ``agent_id``: its own subject's branch when the plan assigns one, else the task's."""
        return self._agent_branches.get(agent_id or "", (self.branch, self.profile))

    def _subject_for(self, agent_id: Optional[str]) -> str:
        return self.plan.agent_subjects.get(agent_id or "", self.plan.subject)

    def _task_type_for(self, agent_id: Optional[str]) -> str:
        return self.plan.agent_task_types.get(agent_id or "", self.plan.task_type)

    # ------------------------------------------------------------------ requests
    #: Most characters of a request text (the TaskRequest contract's bound).
    _MAX_REQUEST_CHARS = 400_000
    #: Most supplied texts one request carries (the TaskRequest contract's bound).
    _MAX_SUPPLIED = 16

    def request(self, from_agent_id: str, to_agent_id: str, user_input: str, supplied_texts: list[SuppliedText] = (),
                *, items=None, constraints=None) -> tuple[Optional[AgentMessage], TaskRequest, TransmissionReceipt]:
        """Make the router's request explicit (items, constraints, texts) and send it in an envelope. Never raises: a request
        the contract cannot carry (a sender or addressee that is no identifier, a request text that is not text, is empty or
        is longer than 400,000 characters, more than 16 supplied texts, anything else that does not validate) is REJECTED
        with INT-REQ-009 saying why, and the returned record holds what could be read of it. Items and constraints beyond
        the contract's 64 each are counted (INT-REQ-018, a warning), never dropped silently; identical constraints are stated
        once. A peer document (``peer:<task>``) whose author delivered a report on this channel must be that report's
        original response word for word (INT-HANDOFF-013 otherwise, :meth:`_peer_documents`): router-side receipts and
        findings never reach a dependent agent as its colleague's report."""
        problems: list[str] = []
        from_id, to_id = _valid_id(from_agent_id), _valid_id(to_agent_id)
        if from_id is None:
            problems.append(f"the request's sender id {_shown_id(from_agent_id)!r} is not a string of 1 to {_ID_MAX} characters")
        if to_id is None:
            problems.append(f"the request's addressee id {_shown_id(to_agent_id)!r} is not a string of 1 to {_ID_MAX} characters")
        if not isinstance(user_input, str):
            problems.append(f"the request text is a {type(user_input).__name__}, not text")
            user_input = ""
        bad_input = surrogate_offsets(user_input)
        if bad_input:  # a request that is not valid Unicode is built on the scrubbed text for the record and REJECTED below
            user_input = _scrub(user_input)
        if _asks_nothing(user_input) and isinstance(user_input, str) and not any("not text" in p for p in problems):
            problems.append("the request text is empty: it asks nothing (it holds no visible character)")
        elif len(user_input) > self._MAX_REQUEST_CHARS:
            problems.append(f"the request text has {len(user_input):,} characters; the contract holds at most {self._MAX_REQUEST_CHARS:,}")
        texts = list(supplied_texts) if isinstance(supplied_texts, (list, tuple)) else []
        if not isinstance(supplied_texts, (list, tuple)):
            problems.append(f"the supplied texts are a {type(supplied_texts).__name__}, not a list of texts")
        unreadable = [k for k, t in enumerate(texts) if not isinstance(t, SuppliedText)]
        if unreadable:
            problems.append(f"supplied text(s) at position(s) {unreadable[:8]} are not supplied-text records")
            texts = [t for t in texts if isinstance(t, SuppliedText)]
        if len(texts) > self._MAX_SUPPLIED:
            problems.append(f"the request carries {len(texts)} supplied texts; the contract holds at most {self._MAX_SUPPLIED}")
        hooks = self._branch_for(to_id)[0].hub_hooks
        n_items = n_constraints = 0
        if problems:
            item_list, constraint_list = [], []
        else:
            if items is not None:
                item_list = list(items)[:MAX_ITEMS]
                n_items = max(0, len(list(items)) - MAX_ITEMS)
            else:
                item_list, n_items = extract_items_counted(user_input, extra_imperatives=hooks.request_imperatives) if hooks else extract_items_counted(user_input)
            if constraints is not None:
                constraint_list = list(constraints)[:MAX_CONSTRAINTS]
                n_constraints = max(0, len(list(constraints)) - MAX_CONSTRAINTS)
            else:
                constraint_list, n_constraints = extract_constraints_counted(user_input)
        stand_in = user_input[:self._MAX_REQUEST_CHARS] if user_input.strip() else "(no request text)"
        try:
            req = TaskRequest(
                request_id=self.plan.request_id, task_id=self.plan.task_id, plan_id=self.plan.plan_id,
                from_agent_id=from_id or "unknown", to_agent_id=to_id or "unknown", subject=self._subject_for(to_id), course_level=self.plan.course_level,
                task_type=self._task_type_for(to_id), user_input=stand_in, user_input_sha256=sha256_hex(stand_in),
                items=item_list, constraints=constraint_list, supplied_texts=texts[:self._MAX_SUPPLIED], created_at=_now(),
            )
        except (ValidationError, TypeError, ValueError) as exc:  # anything else the contract refuses: recorded, never raised
            problems.append(f"the request does not validate against the task_request contract: {_shape_reason(exc, 'task_request')}")
            req = TaskRequest(request_id=self.plan.request_id, task_id=self.plan.task_id, plan_id=self.plan.plan_id, from_agent_id=from_id or "unknown",
                              to_agent_id=to_id or "unknown", subject=self._subject_for(to_id), course_level=self.plan.course_level, task_type=self._task_type_for(to_id),
                              user_input=stand_in, user_input_sha256=sha256_hex(stand_in), created_at=_now())
        findings: list[IntegrityFinding] = []
        agent_ids = [to_id] if to_id else []
        if bad_input:
            findings.append(IntegrityFinding(code="INT-REQ-009", severity="error", message=_surrogate_message("request text", bad_input), agent_ids=agent_ids))
        if problems:
            findings.append(IntegrityFinding(code="INT-REQ-009", severity="error", message="the request cannot be sent: " + "; ".join(problems) + "; it was not delivered", agent_ids=agent_ids))
        if to_id is not None and to_id not in self.plan.selected_agent_ids:
            findings.append(IntegrityFinding(code="INT-HANDOFF-002", severity="error", message=f"router addressed {to_id}, which the plan did not select", agent_ids=[to_id]))
        if self.plan.allowed_document_ids:
            outside = sorted({t.document_id for t in texts if t.document_id not in set(self.plan.allowed_document_ids)})
            if outside:
                findings.append(IntegrityFinding(code="INT-HANDOFF-004", severity="error", message=f"request carries documents outside the retrieval scope: {outside}", document_ids=outside))
        if to_id is not None:
            findings += self._guarded("peer documents (INT-HANDOFF-013)", findings, lambda: self._peer_documents(to_id, texts), [], agent_ids=[to_id])
        if n_items or n_constraints:
            what = " and ".join(x for x in (f"{n_items} more item(s) beyond the {MAX_ITEMS} the contract holds" if n_items else "",
                                            f"{n_constraints} more constraint(s) beyond the {MAX_CONSTRAINTS} the contract holds" if n_constraints else "") if x)
            findings.append(IntegrityFinding(code="INT-REQ-018", severity="warning", message=f"the request states {what}: those were not extracted, so no check covers them; the first {MAX_ITEMS} of each are checked", agent_ids=agent_ids))
        payload = req.model_dump(mode="json", exclude_none=True)
        msg = AgentMessage(message_id=uuid.uuid4().hex, request_id=req.request_id, task_id=req.task_id, sender_agent_id=from_id or "unknown",
                           sender_role=AgentRole.ROUTER, recipient_role=AgentRole.SPECIALIST, recipient_agent_id=to_id or "unknown",
                           contract="task_request/1.0", payload=payload, payload_sha256=payload_hash(payload), created_at=req.created_at)
        findings += self.log.accept(msg)
        status = (TransmissionStatus.REJECTED if any(f.severity == "error" for f in findings) else
                  TransmissionStatus.ACCEPTED_WITH_FINDINGS if any(f.code == "INT-REQ-018" for f in findings) else TransmissionStatus.ACCEPTED)
        if status is not TransmissionStatus.REJECTED:
            self.requests[msg.message_id] = req
            self.router_ids.add(from_id)
        receipt = self._receipt(msg.message_id, "router_to_specialist", status, findings, summary=self._summary_request(req, findings, status))
        return (msg if status is not TransmissionStatus.REJECTED else None), req, receipt

    def _peer_documents(self, to_agent_id: str, texts: list[SuppliedText]) -> list[IntegrityFinding]:
        """INT-HANDOFF-013 (error) for a supplied peer document (``peer:<task>``, or a text credited to a specialist) that is
        a changed copy of a colleague's report delivered on this channel, or a delivered report credited to another agent:
        when a report of the document's author (of any agent, for a document credited to nobody) was delivered here, the
        document must be the original response of one of them word for word; router-side receipt text, or findings added
        before or after the report, never reach a dependent agent as its colleague's report (E2E B3). A peer document whose
        author delivered nothing on this channel, and whose text is no report delivered here, has nothing here to be
        compared with and is not judged by this check."""
        from ..adapters.sources import is_peer_text
        out: list[IntegrityFinding] = []
        delivered = list(self.transmitted_reports.values())
        for t in texts:
            if not is_peer_text(t):
                continue
            author = (t.author or "").strip()
            same = [r for r in delivered if r.original_response == t.text]
            if same and author and author not in {r.agent_id for r in same}:
                out.append(IntegrityFinding(code="INT-HANDOFF-013", severity="error",
                                            message=(f"request supplies peer document {t.document_id!r} credited to {author!r}, but its text is the report "
                                                     f"{same[0].report_id!r} of {same[0].agent_id!r} delivered on this channel: a peer document is credited to "
                                                     f"its author; not delivered"),
                                            document_ids=[t.document_id], agent_ids=sorted({to_agent_id, author, same[0].agent_id}), report_ids=[same[0].report_id]))
                continue
            candidates = [r for r in delivered if r.agent_id == author] if author and any(r.agent_id == author for r in delivered) else ([] if author else delivered)
            if not candidates:
                continue
            match = [r for r in candidates if r.original_response == t.text]
            if not match:
                whose = f"{author!r}'s report(s)" if author else "any report"
                out.append(IntegrityFinding(code="INT-HANDOFF-013", severity="error",
                                            message=(f"request supplies peer document {t.document_id!r} to {to_agent_id!r}, but its text is not the original response of "
                                                     f"{whose} delivered on this channel (a changed copy, or receipt text or findings added to it): a peer document "
                                                     f"must be the colleague's report exactly as it was delivered; not delivered"),
                                            document_ids=[t.document_id], agent_ids=sorted({to_agent_id, *([author] if author else [])}),
                                            report_ids=[r.report_id for r in candidates][:8]))
        return out

    # ----------------------------------------------------------------- responses
    def _quotation_task(self, agent_id: object):
        """The quotation roles of everything the channel reads for ``agent_id``'s delivery are read in the task type the
        plan sets for that agent (``markdown.quotation_task``, authoritative): a report or a synthesis that names another task
        type of its own cannot widen the correction and suggestion roles (repair round 4, INV-Q1)."""
        from ..adapters.markdown import quotation_task
        return quotation_task(self._task_type_for(agent_id if isinstance(agent_id, str) else None), authoritative=True)

    def respond_text(self, request_message_id: str, text: str, *, agent_id: str, report_id: str, supplied_texts: Optional[list[SuppliedText]] = None,
                     agent_version: Optional[str] = None) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        """Parse a specialist's raw text and deliver it (:meth:`_respond_text`), reading its quotations in the plan's task
        type for the agent."""
        with self._quotation_task(agent_id):
            return self._respond_text(request_message_id, text, agent_id=agent_id, report_id=report_id, supplied_texts=supplied_texts,
                                      agent_version=agent_version)

    def _respond_text(self, request_message_id: str, text: str, *, agent_id: str, report_id: str, supplied_texts: Optional[list[SuppliedText]] = None,
                      agent_version: Optional[str] = None) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        """Parse a specialist's raw text with the branch's adapter, then run ``respond``.

        The hub-stated ``agent_id`` is checked against the request's addressee and the plan
        BEFORE parsing (INT-REQ-001 / INT-HANDOFF-002, REJECTED), so identity never depends
        on what the adapter writes into the report; the parsed report is then bound to that
        sender (INT-ENV-008 if the adapter relabelled it). Text the adapter cannot turn into
        a valid report (empty, over the contract limits, malformed) yields a REJECTED receipt
        with INT-REQ-009; nothing raises. Identifiers the hub hands over in another form than a string of 1 to 128
        characters are refused the same way: a request message id that is none replies to no accepted request (INT-REQ-000),
        an agent id or report id that is none cannot bind the text to a sender or a report (INT-REQ-009). Text that is a JSON
        object written out ('{"report_id": ...') is read as JSON: a whole report goes through the report path, a truncated or
        malformed one, or one followed by more text, is refused with INT-REQ-009 naming the malformation, never parsed as
        prose. An answer delivered as a one-key answer object ('{"answer": "..."}', :data:`_ANSWER_ENVELOPE_KEYS`) is read as
        the text it holds (repair round 1, re-run review rc-7 residual); an answer that is one quotation in double quotes
        stays a quotation, checked as one."""
        if not isinstance(text, str):  # a structured payload (a JSON object as received) or nothing: never parsed as text
            return self._respond_payload(request_message_id, text, agent_id=agent_id, report_id=report_id)
        rid_msg = _valid_id(request_message_id)
        req = self.requests.get(rid_msg) if rid_msg is not None else None
        bad_ids = [f"{name} {_shown_id(v)!r}" for name, v in (("agent id", agent_id), ("report id", report_id)) if _valid_id(v) is None]
        shown_agent, shown_report = (_valid_id(agent_id) or (_scrub(agent_id)[:_ID_MAX] if isinstance(agent_id, str) else "")), (_valid_id(report_id) or (_scrub(report_id)[:_ID_MAX] if isinstance(report_id, str) else ""))
        branch, _profile = self._branch_for(shown_agent or None)
        if bad_ids:
            return self._withheld_text(rid_msg, text, agent_id=shown_agent, report_id=shown_report, branch_key=branch.key, findings=[
                IntegrityFinding(code="INT-REQ-009", severity="error", message=f"raw response text arrived with an unreadable {' and '.join(bad_ids)} (an identifier is a string of 1 to {_ID_MAX} characters): the hub cannot bind it to a sender or a report, so it was not parsed or delivered",
                                 report_ids=[shown_report] if shown_report else [], agent_ids=[shown_agent] if shown_agent else [])])
        texts = supplied_texts if supplied_texts is not None else (req.supplied_texts if req else [])
        agent_id, report_id = shown_agent, shown_report
        identity = self._sender_identity(agent_id, req)
        if identity:
            return self._withheld_text(rid_msg, text, agent_id=agent_id, report_id=report_id, branch_key=branch.key, findings=identity)
        bad = surrogate_offsets(text)
        if bad:  # not valid Unicode: no adapter or contract can take it, so it is refused before parsing (never an exception)
            return self._withheld_text(rid_msg, text, agent_id=agent_id, report_id=report_id, branch_key=branch.key, findings=[
                IntegrityFinding(code="INT-REQ-009", severity="error", message=_surrogate_message("response text", bad), report_ids=[report_id], agent_ids=[agent_id])])
        inner = _answer_in_envelope(text)
        if inner is not None and not surrogate_offsets(inner):  # the answer delivered in a one-key answer object
            text = inner
        cut = _cut_structured_reply(text) if inner is None else None
        if cut is not None:  # a structured reply cut off, or a report after prose: refused, never parsed as prose
            return self._withheld_text(rid_msg, text, agent_id=agent_id, report_id=report_id, branch_key=branch.key, findings=[
                IntegrityFinding(code="INT-REQ-009", severity="error", message=f"response text from {agent_id!r} is {cut}; it was not parsed as prose and not delivered",
                                 report_ids=[report_id], agent_ids=[agent_id])])
        body = _json_text(text)
        if body is not None:  # a report written out as JSON: read as JSON, never as prose
            try:
                obj = json.loads(body)
            except json.JSONDecodeError as exc:
                if exc.msg.startswith("Extra data"):
                    # a whole JSON report followed by more text ('{"report_id": ...}}}'): its first value is a report, and what
                    # follows it is no part of it, so it is refused as malformed, never read as prose (re-run review rc-8)
                    try:
                        first, end = json.JSONDecoder().raw_decode(body)
                    except (ValueError, RecursionError):
                        first, end = None, 0
                    if isinstance(first, Mapping) and any(k in first for k in _REPORT_KEYS):
                        return self._withheld_text(rid_msg, text, agent_id=agent_id, report_id=report_id, branch_key=branch.key, findings=[
                            IntegrityFinding(code="INT-REQ-009", severity="error", message=f"response text from {agent_id!r} is a JSON report followed by {len(body) - end:,} more "
                                             f"character(s) at character {end:,} (malformed JSON: {exc.msg}); it was not parsed as prose and not delivered",
                                             report_ids=[report_id], agent_ids=[agent_id])])
                else:
                    cut = exc.msg.startswith("Unterminated") or exc.pos >= len(body.rstrip()) - 1
                    what = (f"a JSON object cut off at character {exc.pos:,} of {len(body):,} (truncated in transit: {exc.msg})" if cut
                            else f"malformed JSON ({exc.msg} at character {exc.pos:,})")
                    return self._withheld_text(rid_msg, text, agent_id=agent_id, report_id=report_id, branch_key=branch.key, findings=[
                        IntegrityFinding(code="INT-REQ-009", severity="error", message=f"response text from {agent_id!r} opens as a JSON report but is {what}; it was not parsed as prose and not delivered",
                                         report_ids=[report_id], agent_ids=[agent_id])])
            else:
                if isinstance(obj, Mapping) and any(k in obj for k in _REPORT_KEYS):
                    return self._respond_payload(rid_msg, obj, agent_id=agent_id, report_id=report_id)
                if not isinstance(obj, Mapping):
                    return self._withheld_text(rid_msg, text, agent_id=agent_id, report_id=report_id, branch_key=branch.key, findings=[
                        IntegrityFinding(code="INT-REQ-009", severity="error", message=f"response text from {agent_id!r} is a JSON {type(obj).__name__}, which is neither response text nor a specialist report; it was not delivered",
                                         report_ids=[report_id], agent_ids=[agent_id])])
        parser = branch.parser()
        extra = {"request_text": req.user_input} if (req is not None and getattr(parser, "accepts_request_text", False) is True) else {}
        if getattr(parser, "accepts_task_agents", False) is True:
            # the agents of this agent's branch that delivered on this task, and this one (E2E B17): with two or more, a STEM
            # parser qualifies its claim ids by agent, so two agents of one STEM branch (Chemistry and ESS) never share an id.
            # Agents of another branch number with their own letter (s, m, c) and cannot collide, and the set is
            # delivery-based, so a plan naming an agent that delivers nothing (a combinator) keeps plain ids
            same_branch = {r.agent_id for r in self.transmitted_reports.values() if self._branch_for(r.agent_id)[0].key == branch.key}
            extra["task_agent_ids"] = sorted(same_branch | {agent_id})
        try:
            report = parser.parse_response(text, request_id=self.plan.request_id, task_id=self.plan.task_id, report_id=report_id, subject=self._subject_for(agent_id),
                                           task_type=self._task_type_for(agent_id), supplied_texts=list(texts), course_level=self.plan.course_level or "unknown", agent_version=agent_version, agent_id=agent_id,
                                           **extra)
        except Exception as exc:  # adapter and contract errors become a rejection, never an exception out of the hub
            return self._withheld_text(rid_msg, text, agent_id=agent_id, report_id=report_id, branch_key=branch.key, findings=[
                IntegrityFinding(code="INT-REQ-009", severity="error", message=f"response could not be parsed into a report by branch {branch.key}: {type(exc).__name__}: {_shape_reason(exc, 'specialist_report')}", report_ids=[report_id], agent_ids=[agent_id])])
        return self.respond(rid_msg, report, sender_agent_id=agent_id)

    def _respond_payload(self, request_message_id: str, payload, *, agent_id: str, report_id: str) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        """A response handed over as something other than text: a mapping (a report as JSON received over the wire) is
        validated against the specialist_report contract and then checked like any report, its sender being the agent
        the hub states; anything else, or a mapping that does not validate, is REJECTED with INT-REQ-009. Nothing raises."""
        rid_msg = _valid_id(request_message_id)
        agent_id = _scrub(agent_id)[:_ID_MAX] if isinstance(agent_id, str) else ""
        report_id = _scrub(report_id)[:_ID_MAX] if isinstance(report_id, str) else ""
        branch, _profile = self._branch_for(agent_id or None)
        if isinstance(payload, SpecialistReport):
            return self.respond(rid_msg, payload, sender_agent_id=agent_id or None)
        if isinstance(payload, Mapping):
            provenance = _raw_claim_provenance(payload)
            if provenance:  # a claim of another report inside this one: named as such, never a bare contract value error
                return self._withheld_payload(rid_msg, payload, agent_id=agent_id, report_id=report_id, branch_key=branch.key, message="", findings=provenance)
            try:
                report = _strict_contract(SpecialistReport, dict(payload))
            except (ValidationError, TypeError, ValueError) as exc:
                why = f"a mapping that does not validate against the specialist_report contract: {_shape_reason(exc, 'specialist_report')}"
            else:
                return self.respond(rid_msg, report, sender_agent_id=agent_id or None)
        else:
            why = f"a payload of type {type(payload).__name__}, which is neither response text nor a specialist report"
        return self._withheld_payload(rid_msg, payload, agent_id=agent_id, report_id=report_id, branch_key=branch.key,
                                      message=f"response from {agent_id!r} is {why}; it was not delivered")

    def _withheld_payload(self, in_reply_to: Optional[str], payload, *, agent_id: str, report_id: str, branch_key: str, message: str,
                          sender_role: AgentRole = AgentRole.SPECIALIST, recipient_role: AgentRole = AgentRole.ROUTER, recipient_agent_id: Optional[str] = None,
                          findings: Optional[list[IntegrityFinding]] = None, named: Optional[list[IntegrityFinding]] = None) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        """A payload the channel cannot read as a contract (or, with ``findings``, one it refuses before validation: a claim
        carrying another report's provenance, INT-HANDOFF-012): the envelope carries its type and digest only; REJECTED
        with INT-REQ-009 naming ``message``, or with the given findings. ``named`` are findings that say more precisely
        what made the payload unreadable (INT-SYNTH-014: a value outside a closed vocabulary of the synthesis contract);
        they are added after the INT-REQ-009, which still refuses the payload. Every identifier is put in the form the
        envelope contract takes (an unreadable one becomes None or "unknown"), so this refusal itself never raises."""
        try:
            digest = payload_hash(payload) if isinstance(payload, (Mapping, list)) else sha256_hex(repr(payload))
        except Exception:
            digest = sha256_hex(repr(type(payload)))
        agent_id = _scrub(agent_id)[:_ID_MAX] if isinstance(agent_id, str) else ""
        report_id = _scrub(report_id)[:_ID_MAX] if isinstance(report_id, str) else ""
        body = {"report_id": report_id, "agent_id": agent_id, "request_id": self.plan.request_id, "task_id": self.plan.task_id,
                "payload_type": type(payload).__name__, "payload_sha256": digest}
        msg = AgentMessage(message_id=uuid.uuid4().hex, request_id=self.plan.request_id, task_id=self.plan.task_id, sender_agent_id=agent_id or "unknown",
                           sender_role=_role_of(sender_role) or AgentRole.SPECIALIST, recipient_role=_role_of(recipient_role) or AgentRole.ROUTER,
                           recipient_agent_id=_valid_id(recipient_agent_id), contract="unreadable_payload/1.0",
                           payload=body, payload_sha256=payload_hash(body), in_reply_to=_valid_id(in_reply_to), created_at=_now())
        given = [f.model_copy(update={"message_ids": sorted(set(f.message_ids) | {msg.message_id})}) for f in findings] if findings else None
        findings = self.log.accept(msg) + (given or [IntegrityFinding(code="INT-REQ-009", severity="error", message=message, report_ids=[report_id] if report_id else [], agent_ids=[agent_id] if agent_id else [], message_ids=[msg.message_id])])
        findings += [f.model_copy(update={"message_ids": sorted(set(f.message_ids) | {msg.message_id})}) for f in (named or [])]
        return self._finish(msg, "specialist_to_router" if msg.recipient_role is AgentRole.ROUTER and msg.sender_role is AgentRole.SPECIALIST else "agent_to_agent", findings, [], [], [], branch_key=branch_key)

    def _sender_identity(self, agent_id: str, req: Optional[TaskRequest]) -> list[IntegrityFinding]:
        """Identity of a raw-text sender, decided from the hub's statement alone."""
        out: list[IntegrityFinding] = []
        if agent_id not in self.plan.selected_agent_ids:
            out.append(IntegrityFinding(code="INT-HANDOFF-002", severity="error", message=f"response stated to come from {agent_id!r}, which the plan did not select (selected: {self.plan.selected_agent_ids}); the text was not parsed", agent_ids=[agent_id]))
        if req is not None and agent_id != req.to_agent_id:
            out.append(IntegrityFinding(code="INT-REQ-001", severity="error", message=f"response stated to come from {agent_id!r} but the request was addressed to {req.to_agent_id!r}; the text was not parsed", agent_ids=sorted({agent_id, req.to_agent_id})))
        return out

    def _withheld_text(self, request_message_id: str, text: str, *, agent_id: str, report_id: str, branch_key: str, findings: list[IntegrityFinding]) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        """Raw text that is not parsed into a report (unknown sender, unparseable): the envelope carries only the digest
        (every identifier in the form the envelope takes, so the refusal never raises)."""
        agent_id = _scrub(agent_id)[:_ID_MAX] if isinstance(agent_id, str) else ""
        report_id = _scrub(report_id)[:_ID_MAX] if isinstance(report_id, str) else ""
        payload = {"report_id": report_id, "agent_id": agent_id, "request_id": self.plan.request_id, "task_id": self.plan.task_id,
                   "response_sha256": sha256_text(text), "response_chars": len(text)}
        msg = AgentMessage(message_id=uuid.uuid4().hex, request_id=self.plan.request_id, task_id=self.plan.task_id, sender_agent_id=agent_id or "unknown",
                           sender_role=AgentRole.SPECIALIST, recipient_role=AgentRole.ROUTER, contract="specialist_report/1.0",
                           payload=payload, payload_sha256=payload_hash(payload), in_reply_to=_valid_id(request_message_id), created_at=_now())
        all_findings = self.log.accept(msg) + [f.model_copy(update={"message_ids": sorted(set(f.message_ids) | {msg.message_id})}) for f in findings]
        return self._finish(msg, "specialist_to_router", all_findings, [], [], [], branch_key=branch_key)

    def _revalidate(self, report: SpecialistReport, payload: dict) -> list[IntegrityFinding]:
        """The payload delivered to the recipient must re-validate against the contract;
        a report built around validation (model_copy) is caught here, not downstream. A claim
        whose ``report_id`` or ``request_id`` differs from its report is a provenance fault and
        is named as one (INT-HANDOFF-012, with the claim and the fields) on the raw payload,
        not reported as a bare contract value error."""
        out: list[IntegrityFinding] = []
        for raw in payload.get("claims", []) or []:
            if not isinstance(raw, dict):
                continue
            mismatch = [n for n, key in (("report_id", "report_id"), ("request_id", "request_id")) if raw.get(key) != payload.get(key)]
            if mismatch:
                cid = str(raw.get("claim_id", "?"))
                out.append(IntegrityFinding(code="INT-HANDOFF-012", severity="error", message=f"claim {cid} carries provenance that differs from its report in {mismatch} (claim {[raw.get(k) for k in mismatch]} vs report {[payload.get(k) for k in mismatch]}): a claim of another report or request hidden inside this one; not delivered",
                                            claim_ids=[cid], report_ids=[report.report_id], agent_ids=[report.agent_id]))
        try:
            SpecialistReport.model_validate(payload)
        except ValidationError as exc:
            errors = exc.errors()
            if out:  # the provenance fault is already named; only report what else failed
                errors = [e for e in errors if "does not belong to this report" not in str(e.get("msg", "")) and "does not belong to this report" not in str(e.get("ctx", {}).get("error", ""))]
            if errors:
                out.append(IntegrityFinding(code="INT-REQ-009", severity="error", message=f"report payload does not re-validate against the specialist_report contract and is not delivered: {_shape_reason(exc)}",
                                            report_ids=[report.report_id], agent_ids=[report.agent_id]))
        return out

    @staticmethod
    def _substituted_texts(req: TaskRequest, report: SpecialistReport, msg: AgentMessage) -> list[IntegrityFinding]:
        """INT-REQ-002 (error, blocking) for a report that carries a supplied text the request did not send (also when the
        request sent none), or another text under a document id the request sent: the specialist would supply the source
        its own quotations are checked against. Compared by document id and the whole record: the text (each reported with
        its digest) and its metadata, the title, author, locator scheme and provenance the quotation credits read (repair
        round 1, re-run review security-3 variant: the same text under another author is another record)."""
        sent = {t.document_id: t for t in req.supplied_texts}
        extra = sorted({t.document_id for t in report.supplied_texts if t.document_id not in sent})
        changed = sorted({t.document_id for t in report.supplied_texts if t.document_id in sent and t.text != sent[t.document_id].text})
        relabelled = sorted({t.document_id for t in report.supplied_texts
                             if t.document_id in sent and t.text == sent[t.document_id].text and t.model_dump() != sent[t.document_id].model_dump()})
        ids = dict(report_ids=[report.report_id], agent_ids=[report.agent_id], message_ids=[msg.message_id])
        out: list[IntegrityFinding] = []
        if extra:
            out.append(IntegrityFinding(code="INT-REQ-002", severity="error", document_ids=extra,
                                        message=f"response carries supplied text(s) {extra} that the request did not send ({'it sent none' if not sent else 'it sent ' + str(sorted(sent))}): a specialist cannot supply the source its quotations are checked against; not delivered", **ids))
        if changed:
            digests = {t.document_id: sha256_text(t.text)[:12] for t in report.supplied_texts if t.document_id in changed}
            out.append(IntegrityFinding(code="INT-REQ-002", severity="error", document_ids=changed,
                                        message=f"response carries another text under document id(s) {changed} than the request sent (digests {digests} differ from the router's): the specialist's copy would replace the supplied text; not delivered", **ids))
        if relabelled:
            fields = sorted({k for t in report.supplied_texts if t.document_id in relabelled
                             for k, v in t.model_dump().items() if v != sent[t.document_id].model_dump().get(k)})
            out.append(IntegrityFinding(code="INT-REQ-002", severity="error", document_ids=relabelled,
                                        message=f"response carries the text of document id(s) {relabelled} with other metadata than the request sent (fields {fields}): "
                                                "the specialist's record would replace the router's, and a quotation credit reads the title and author; not delivered", **ids))
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
        for fc in formal:
            if str(getattr(fc, "kind", "")).startswith("stem_") and time.perf_counter() - started > STEM_CHECK_BUDGET_S:
                cids, where, quoted = self._check_claims_named(fc, report)
                ident = dict(claim_ids=cids, report_ids=[report.report_id], agent_ids=[report.agent_id]) if cids else {}
                results.append(ConstraintResult(constraint_id=fc.check_id, satisfied=None, method="formal", claim_ids=cids,
                                                detail=truncate(f"{fc.kind}{where}: {quoted}{fc.description}; not run: the report's STEM check budget ({STEM_CHECK_BUDGET_S:g} s) was spent", _DETAIL_MAX)))
                findings.append(IntegrityFinding(code="INT-SUBJ-002", severity="warning",
                                                 message=f"{fc.kind} check{where} undecided (check budget: the report's STEM checks ran past {STEM_CHECK_BUDGET_S:g} s; not run): {quoted}{fc.description}",
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
    def _check_defect(fc) -> Optional[str]:
        """The defect label of a failed branch formal check: the FormalCheck's own ``defect`` when it is a canonical label, else
        the label of its kind (``named.DEFECT_OF_CHECK_KIND``; None for a kind that names no defect)."""
        own = getattr(fc, "defect", None)
        if isinstance(own, str) and own in DEFECT_LABELS:
            return own
        return defect_of_check_kind(getattr(fc, "kind", None))

    @staticmethod
    def _model_note(fc, res: VerificationResult) -> str:
        """For a STEM check, the counterexample's computed and stated values (symbols ``c`` and ``r``) beside the statement."""
        if not str(getattr(fc, "kind", "")).startswith("stem_") or res.counterexample is None:
            return ""
        shown = [f"{m.symbol} = {m.value}" for m in res.counterexample.assignments if m.symbol in ("c", "r")]
        return f" (engine counterexample: {', '.join(shown)}; c is the value computed from the written expression, r the stated value)" if shown else ""

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

    def respond(self, request_message_id: str, report: SpecialistReport, *, sender_agent_id: Optional[str] = None) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        """Check and deliver a specialist's report (:meth:`_respond`), reading its quotations in the plan's task type for the
        sender (the hub-stated sender, else the report's own agent id)."""
        agent = sender_agent_id if isinstance(sender_agent_id, str) and sender_agent_id else getattr(report, "agent_id", None)
        with self._quotation_task(agent):
            return self._respond(request_message_id, report, sender_agent_id=sender_agent_id)

    def _respond(self, request_message_id: str, report: SpecialistReport, *, sender_agent_id: Optional[str] = None) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        """Check a specialist's report against the request it answers and deliver it with a receipt.

        ``sender_agent_id`` is the agent the hub says sent the report (raw text arriving
        through ``respond_text``); it defaults to the report's own ``agent_id``. The envelope
        is bound to that sender, so a report that claims another author is INT-ENV-008.
        Identity and integrity errors REJECT the transmission before any content check runs
        (nothing is pooled or stored); content findings travel with the delivered report. The quotations and figures of a
        report are checked against the texts the REQUEST supplied, never against the report's own copies: a report that
        carries a text the request did not send, or another text under a document id the request sent, is INT-REQ-002 and
        is not delivered."""
        rid_msg = _valid_id(request_message_id)
        req = self.requests.get(rid_msg) if rid_msg is not None else None
        if not isinstance(report, SpecialistReport):  # never raised: anything else goes to the payload path
            return self._respond_payload(rid_msg, report, agent_id=sender_agent_id if isinstance(sender_agent_id, str) else "", report_id="")
        if sender_agent_id is not None and _valid_id(sender_agent_id) is None:
            return self._withheld_payload(rid_msg, report.model_dump(mode="json", exclude_none=True), agent_id="", report_id=report.report_id, branch_key=self.branch.key,
                                          message=f"report {report.report_id!r} arrived with an unreadable sender id {_shown_id(sender_agent_id)!r} (an identifier is a string of 1 to {_ID_MAX} characters); the hub cannot bind it to a sender, so it was not delivered")
        sender = sender_agent_id or report.agent_id
        findings: list[IntegrityFinding] = []
        payload = report.model_dump(mode="json", exclude_none=True)
        msg = AgentMessage(message_id=uuid.uuid4().hex, request_id=report.request_id, task_id=report.task_id, sender_agent_id=sender,
                           sender_role=AgentRole.SPECIALIST, recipient_role=AgentRole.ROUTER, contract="specialist_report/1.0",
                           payload=payload, payload_sha256=payload_hash(payload), in_reply_to=rid_msg, created_at=_now())
        findings += self.log.accept(msg)
        findings += bind_payload(msg, report)
        findings += self._dedupe(msg)
        findings += self._revalidate(report, payload)
        bk = self._branch_for(sender)[0].key
        if req is None:
            findings.append(IntegrityFinding(code="INT-REQ-000", severity="error", message="response does not reply to any accepted request on this channel" + ("" if rid_msg is not None else f" (its request message id {_shown_id(request_message_id)!r} is not an identifier)"),
                                             message_ids=[msg.message_id] + ([rid_msg] if rid_msg is not None else [])))
            return self._finish(msg, "specialist_to_router", findings, [], [], [], branch_key=bk)
        if any(f.code in ("INT-REQ-009", "INT-HANDOFF-012") for f in findings):  # the payload does not re-validate or carries another report's claims
            return self._finish(msg, "specialist_to_router", findings, [], [], [], branch_key=bk)
        if sender != req.to_agent_id:
            findings.append(IntegrityFinding(code="INT-REQ-001", severity="error", message=f"response came from {sender} but the request was addressed to {req.to_agent_id}", agent_ids=sorted({sender, req.to_agent_id}), message_ids=[msg.message_id]))
        findings += check_report_against_plan(self.plan, report)
        findings += self._report_id_reuse(report, msg, findings)
        supplied = list(req.supplied_texts)  # the router's texts are the only source set: a report's own copy is never one
        findings += self._substituted_texts(req, report, msg)
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
        findings += self._guarded("folded claims (INT-REQ-013)", findings, lambda: self._fold_findings(report, supplied), [], **rid)
        findings += self._guarded("system check results in the answer (INT-REQ-017)", findings, lambda: self._system_check_content(report, supplied), [], **rid)
        branch, profile = self._branch_for(report.agent_id)
        hooks = branch.hub_hooks  # the branch's readings for the hub (the STEM branches only); each refines a heuristic and never raises
        exempt = bool(hooks) and self._hook(lambda: hooks.echo_exempt(report.original_response, req.user_input, profile.key), False)
        echo = None if exempt else self._guarded("request echo (INT-REQ-011)", findings, lambda: self._request_echo(req, report, supplied), None, **rid)
        if echo is not None:
            findings.append(echo)
        view = (lambda t: self._hook(lambda: hooks.word_count_view(t, profile.key), t)) if hooks else None
        findings += self._guarded("answer presence (INT-REQ-012)", findings, lambda: self._no_answer(report, view=view), [], **rid)
        no_answer = any(f.code == "INT-REQ-012" for f in findings)
        coverage = self._guarded("request coverage (INT-REQ-004)", findings, lambda: self._coverage(req, report, echoed=echo is not None, hooks=hooks, profile_key=profile.key, no_answer=no_answer), [], **rid)
        for cov in coverage:
            if not cov.addressed:
                item = next(i for i in req.items if i.item_id == cov.item_id)
                findings.append(IntegrityFinding(code="INT-REQ-004", severity="warning" if item.required else "info", message=f"request item {cov.item_id} appears unaddressed: {item.text[:120]!r} (heuristic)" + (f"; {cov.note}" if getattr(cov, "note", None) else ""), claim_ids=[]))
        # Command terms C6: evaluate / discuss / to what extent / assess / examine / justify / recommend / give a judgement
        # need a judgement or position on degree. A judgement-role claim counts; so does a point, thesis, link or analysis
        # claim that states a position (verdict cue); a bare claim does not. A claim roled 'other' (a note, a self-report) never counts.
        verdict_present = any(c.claim_role == "judgement" or (c.claim_role in _VERDICT_ROLES and _VERDICT_CUE.search(c.claim_text)) for c in report.claims)
        for item in req.items:
            if item.level == 3 and item.command_term in LEVEL3_VERDICT_TERMS and not verdict_present:
                findings.append(IntegrityFinding(code="INT-REQ-008", severity="warning", message=f"item {item.item_id} uses the command term {item.command_term!r}, which requires a judgement or position on degree; no judgement/point claim was found (command terms C6)", claim_ids=[]))
        constraint_results, formal_ids = self._guarded("request constraints (INT-REQ-005)", findings, lambda: self._constraints(req, report, view=view), ([], []), **rid)
        structural, branch_formal, branch_ids = self._branch_checks(report, req, findings, frozenset(covered), frozenset(form_covered))
        refuted = {cid for f in uncredited for cid in f.claim_ids}
        if refuted:  # the same quotation is not also "unverifiable": the hub found it in none of the supplied texts
            structural = [sf for sf in structural if not (sf.code == "CORE-SRC-003" and sf.claim_ids and set(sf.claim_ids) <= refuted)]
        findings = self._name_branch_rules(findings, structural)
        findings += self._guarded("credits to texts not supplied (INT-REQ-015)", findings, lambda: self._foreign_credits(report, supplied, structural), [], **rid)
        formal_ids = list(formal_ids) + branch_ids
        kinds = {c.constraint_id: c.kind for c in req.constraints}
        for cr in constraint_results:
            if cr.satisfied is False:
                # A paragraph bound is measured over blank-line blocks; a specialist may set one paragraph out as several blocks
                # (point, strands, link), so an overrun is a layout warning for the router, not an error like a word limit.
                layout = kinds.get(cr.constraint_id, "").endswith("paragraphs")
                findings.append(IntegrityFinding(code="INT-REQ-005", severity="warning" if layout else "error",
                                                 message=f"constraint {cr.constraint_id} not satisfied: {cr.detail}" + (" (blank-line blocks; a paragraph set out in blocks counts as several)" if layout else ""),
                                                 formal_result_id=cr.formal_result_id, deterministic=cr.method != "formal"))
            elif cr.satisfied is None and cr.method == "not_checkable" and kinds.get(cr.constraint_id, "").endswith("words"):
                # a bound set on a part the answer does not label: never measured on another span, and never silently passed
                findings.append(IntegrityFinding(code="INT-REQ-005", severity="warning", message=f"constraint {cr.constraint_id} could not be checked on its scope: {cr.detail}", deterministic=True))
        self._guarded("supersession (INT-HANDOFF-009)", findings, lambda: self._supersession(report, findings), None, **rid)
        # An echo of the request answers nothing: its outcomes are delivered for the record but never pooled, so its
        # formalizations cannot displace the agent's genuine claims under the same ids.
        outcomes = self._guarded("claim verification", findings, lambda: self._verify_claims(report, findings, pool=echo is None, task=self._task_record(req)), [], **rid)
        report_named = self._guarded("argument diagnosis (report level)", findings, lambda: self._report_diagnosis(report, req, outcomes), None, **rid)
        if not _is_blocking(findings):  # delivered <=> transmitted: a synthesis may cite any report the router received
            self.transmitted_reports.setdefault(report.report_id, report)
        return self._finish(msg, "specialist_to_router", findings, coverage, constraint_results, outcomes, formal_ids, structural=structural, branch_formal=branch_formal, branch_key=bk,
                            report=report, report_named=report_named)

    # --------------------------------------------------------------- agent relay
    def relay(self, from_agent_id: str, from_role: AgentRole, to_agent_id: str, to_role: AgentRole,
              payload_obj: Union[SpecialistReport, Synthesis], in_reply_to: Optional[str] = None) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        """Carry a report or a synthesis (:meth:`_relay`), reading its quotations in the plan's task type for the sender."""
        with self._quotation_task(from_agent_id):
            return self._relay(from_agent_id, from_role, to_agent_id, to_role, payload_obj, in_reply_to)

    def _relay(self, from_agent_id: str, from_role: AgentRole, to_agent_id: str, to_role: AgentRole,
               payload_obj: Union[SpecialistReport, Synthesis], in_reply_to: Optional[str] = None) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        """Carry a report or a synthesis between agents. A payload handed over as a mapping (JSON as received) is validated
        against the contract its shape names (``synthesis_id``: synthesis/1.0, ``report_id``: specialist_report/1.0) first;
        anything else, or a mapping that does not validate, is REJECTED with INT-REQ-009 and nothing raises. So are parties
        the envelope cannot carry: an agent id that is no string of 1 to 128 characters, a role that is no agent role (a
        role given as its string value, "router", is that role), an ``in_reply_to`` that is no message id; they are refused
        before the payload is read or checked (the log holds only the refusal's own envelope: the payload's type and digest).
        A report relayed by an agent (not a router forward) is a hand-off of a report its sender
        already delivered on this channel, unchanged: any other report is INT-HANDOFF-013 and enters no channel state (new
        reports arrive only through ``respond``, in reply to an accepted request). A router forward replies to the delivery
        of the report it carries: an ``in_reply_to`` that names another message is INT-HANDOFF-013; with none, the channel
        ties the forward to the report's first delivery to that router itself, in the forward's own envelope
        (``in_reply_to``), so the ledger never holds a forward cut loose from the delivery it carries on, and names the gap
        (INT-HANDOFF-018, warning). A synthesis that fails on a value outside one of the contract's closed vocabularies (a transformation
        written as free text, say) is also named with INT-SYNTH-014; a synthesis object built around validation is
        re-validated and refused the same way (``_revalidate_synthesis``)."""
        fr, tr = _role_of(from_role), _role_of(to_role)
        from_id, to_id = _valid_id(from_agent_id), _valid_id(to_agent_id)
        reply_id = _valid_id(in_reply_to) if in_reply_to is not None else None
        bad_parties = ([f"from_role {_shown_id(from_role) if not isinstance(from_role, AgentRole) else from_role.value!r}"] if fr is None else []) \
            + ([f"to_role {_shown_id(to_role) if not isinstance(to_role, AgentRole) else to_role.value!r}"] if tr is None else []) \
            + ([f"from_agent_id {_shown_id(from_agent_id)!r}"] if from_id is None else []) + ([f"to_agent_id {_shown_id(to_agent_id)!r}"] if to_id is None else []) \
            + ([f"in_reply_to {_shown_id(in_reply_to)!r}"] if in_reply_to is not None and reply_id is None else [])
        if bad_parties:
            rid = ""
            if isinstance(payload_obj, (SpecialistReport, Synthesis)):
                rid = payload_obj.report_id if isinstance(payload_obj, SpecialistReport) else payload_obj.synthesis_id
            elif isinstance(payload_obj, Mapping):
                raw = payload_obj.get("report_id") or payload_obj.get("synthesis_id") or ""
                rid = raw if isinstance(raw, str) else ""
            return self._withheld_payload(None, payload_obj.model_dump(mode="json", exclude_none=True) if isinstance(payload_obj, BaseModel) else payload_obj,
                                          agent_id=from_id or "", report_id=rid, branch_key=self.branch.key,
                                          message=f"relay carries parties the envelope cannot take ({'; '.join(bad_parties)}: an agent id is a string of 1 to {_ID_MAX} characters, a role one of {[r.value for r in AgentRole]}, in_reply_to a message id); it was not delivered",
                                          sender_role=fr or AgentRole.SPECIALIST, recipient_role=tr or AgentRole.ROUTER, recipient_agent_id=to_id)
        from_role, to_role, from_agent_id, to_agent_id, in_reply_to = fr, tr, from_id, to_id, reply_id
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
        router_named_delivery = in_reply_to is not None
        if forward and in_reply_to is None:
            # a forward that names no delivery is tied, in its own envelope, to the report's first delivery to this router
            tie = next((mid for mid in self.delivered_to_router.get(payload_obj.report_id, [])
                        if (got := self.log.get(mid)) is not None and got.recipient_agent_id in (None, from_agent_id)), None)
            in_reply_to = tie
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
        findings += self.log.accept(msg)
        if not forward:  # a forward carries another agent's report by design; every other relay must come from the payload's owner
            findings += bind_payload(msg, payload_obj)
        findings += self._dedupe(msg)
        findings += self._relay_parties(msg, from_role, to_agent_id, to_role, payload_obj)
        if payload_obj.request_id != self.plan.request_id or payload_obj.task_id != self.plan.task_id:
            findings.append(IntegrityFinding(code="INT-HANDOFF-001", severity="error", message="relayed payload belongs to another request/task", message_ids=[msg.message_id]))
        outcomes: list[ClaimVerificationOutcome] = []
        structural: list[StructuralFinding] = []
        branch_formal: list[ConstraintResult] = []
        branch_ids: list[str] = []
        history: list[ReceiptReference] = []
        bk = self._branch_for(payload_obj.agent_id)[0].key if isinstance(payload_obj, SpecialistReport) else self.branch.key
        if isinstance(payload_obj, SpecialistReport):
            findings += self._revalidate(payload_obj, payload)
            if any(f.code in ("INT-REQ-009", "INT-HANDOFF-012") for f in findings):
                return self._finish(msg, "agent_to_agent", findings, [], [], [], branch_key=bk)
            if forward:
                # The router may only pass on a report exactly as it was delivered on this channel: same report id,
                # same payload digest. Anything else is a report altered in transit or never received.
                held = self.transmitted_reports.get(payload_obj.report_id)
                if held is None:
                    findings.append(IntegrityFinding(code="INT-HANDOFF-013", severity="error", message=f"router forwarded report {payload_obj.report_id!r}, which was never delivered on this channel", report_ids=[payload_obj.report_id], agent_ids=[from_agent_id, to_agent_id], message_ids=[msg.message_id]))
                elif payload_hash(held.model_dump(mode="json", exclude_none=True)) != msg.payload_sha256:
                    findings.append(IntegrityFinding(code="INT-HANDOFF-013", severity="error", message=f"router forwarded report {payload_obj.report_id!r} with a payload that differs from the one delivered on this channel (altered in transit)", report_ids=[payload_obj.report_id], agent_ids=[from_agent_id, to_agent_id], message_ids=[msg.message_id]))
                deliveries = self.delivered_to_router.get(payload_obj.report_id, [])
                if held is not None and in_reply_to is not None and in_reply_to not in deliveries:
                    findings.append(IntegrityFinding(code="INT-HANDOFF-013", severity="error",
                                                     message=f"router forward of report {payload_obj.report_id!r} replies to message {in_reply_to!r}, which is not the delivery of that report on this channel (delivered as {deliveries[:4]}): a forward is tied to the delivery it carries on; not delivered",
                                                     report_ids=[payload_obj.report_id], agent_ids=[from_agent_id, to_agent_id], message_ids=_dedupe_ids([msg.message_id, in_reply_to, *deliveries[:4]])))
                if _is_blocking(findings):
                    return self._finish(msg, "agent_to_agent", findings, [], [], [], branch_key=bk)
                if in_reply_to is not None or deliveries:  # the delivery this forward carries on: named by the router, or tied by the channel
                    self.forward_of[msg.message_id] = in_reply_to if in_reply_to is not None else deliveries[0]
                if not router_named_delivery:
                    # the router named no delivery: the channel tied the forward to the report's first delivery to it, and says
                    # so (repair round 1, re-run review re-5: a forward with no in_reply_to was delivered with nothing naming the gap)
                    tie = in_reply_to if in_reply_to is not None else (deliveries[0] if deliveries else None)
                    tied = f"the channel tied it to the report's delivery {tie!r}" if tie is not None else "no delivery to the router could be tied to it"
                    findings.append(IntegrityFinding(code="INT-HANDOFF-018", severity="warning",
                                                     message=f"router forward of report {payload_obj.report_id!r} replies to no message (no in_reply_to): a forward replies to the delivery it carries on; {tied}",
                                                     report_ids=[payload_obj.report_id], agent_ids=_dedupe_ids([from_agent_id, to_agent_id]),
                                                     message_ids=_dedupe_ids([msg.message_id, *([tie] if tie else [])])))
                # The delivered report was already parsed, checked and pooled on arrival; a faithful forward re-runs
                # the hand-off checks (plan scope, self-reports) but not the subject packs and verification.
                findings += check_report_against_plan(self.plan, payload_obj)
                if payload_obj.report_id in self.superseded:
                    findings.append(IntegrityFinding(code="INT-HANDOFF-014", severity="warning", message=f"router forwarded report {payload_obj.report_id!r}, which agent {payload_obj.agent_id!r} superseded with report {self.superseded[payload_obj.report_id]!r} on this channel; the recipient receives a superseded report", report_ids=[payload_obj.report_id, self.superseded[payload_obj.report_id]], agent_ids=[payload_obj.agent_id, to_agent_id], message_ids=[msg.message_id]))
                # A forward re-checks nothing: what the report's earlier receipts left unresolved travels with it; to a peer
                # specialist, which builds on the report as material, only the faults the content was found to have (accuracy
                # round 1, DV2-05: _DECIDED_WARNINGS)
                history = self._guarded("relay history (INT-HIST-001)", findings, lambda: self._history_of([("report", payload_obj.report_id)]), [], report_ids=[payload_obj.report_id])
                findings += self._guarded("relay history (INT-HIST-001)", findings, lambda: self._carried(history, findings, decided_only=tr is AgentRole.SPECIALIST),
                                          [], report_ids=[payload_obj.report_id])
                self.forwards.setdefault(payload_obj.report_id, []).append((to_agent_id, msg.message_id))
                return self._finish(msg, "agent_to_agent", findings, [], [], [], branch_key=bk, history=history)
            findings += check_report_against_plan(self.plan, payload_obj)
            findings += self._report_id_reuse(payload_obj, msg, findings)
            if payload_obj.report_id not in self.transmitted_reports:
                # a relay hands on a report its sender already delivered; a new report enters only through respond(), in reply
                # to an accepted request, so one that never arrived changes no channel state (supersession, pool, held reports)
                findings.append(IntegrityFinding(code="INT-HANDOFF-013", severity="error",
                                                 message=f"agent {from_agent_id!r} relays report {payload_obj.report_id!r}, which was never delivered on this channel: a relay hands on a report its sender already delivered, unchanged, and a new report arrives only in reply to an accepted request; not delivered",
                                                 report_ids=[payload_obj.report_id], agent_ids=_dedupe_ids([from_agent_id, payload_obj.agent_id, to_agent_id]), message_ids=[msg.message_id]))
            if _is_blocking(findings):  # identity or integrity violation: nothing of this report is checked for content, pooled or stored
                return self._finish(msg, "agent_to_agent", findings, [], [], [], branch_key=bk)
            rid = dict(report_ids=[payload_obj.report_id], agent_ids=[payload_obj.agent_id])
            findings += self._guarded("claim-id collision", findings, lambda: self._claim_id_collisions(payload_obj), [], **rid)
            findings += self._guarded("folded claims (INT-REQ-013)", findings, lambda: self._fold_findings(payload_obj, payload_obj.supplied_texts), [], **rid)
            structural, branch_formal, branch_ids = self._branch_checks(payload_obj, None, findings)
            findings += self._guarded("credits to texts not supplied (INT-REQ-015)", findings, lambda: self._foreign_credits(payload_obj, payload_obj.supplied_texts, structural), [], **rid)
            self._guarded("supersession (INT-HANDOFF-009)", findings, lambda: self._supersession(payload_obj, findings), None, **rid)
            outcomes = self._guarded("claim verification", findings, lambda: self._verify_claims(payload_obj, findings), [], **rid)
            relayed_named = self._guarded("argument diagnosis (report level)", findings, lambda: self._report_diagnosis(payload_obj, None, outcomes), None, **rid)
            # A relay runs without the request: what the report's earlier receipts left unresolved (a failed Given check,
            # an unaddressed item, a word limit) travels with it, so this receipt never reads cleaner than its history.
            history = self._guarded("relay history (INT-HIST-001)", findings, lambda: self._history_of([("report", payload_obj.report_id)]), [], **rid)
            findings += self._guarded("relay history (INT-HIST-001)", findings, lambda: self._carried(history, findings, structural, decided_only=tr is AgentRole.SPECIALIST),
                                      [], **rid)
            if not _is_blocking(findings):
                self.transmitted_reports.setdefault(payload_obj.report_id, payload_obj)
        else:
            findings += self._revalidate_synthesis(payload_obj, payload)
            findings += self._synthesis_id_reuse(payload_obj, msg, findings)
            if _is_blocking(findings):  # an invalid synthesis, an unselected or impersonating combinator, or a reused synthesis id: its ledger is not examined
                return self._finish(msg, "agent_to_agent", findings, [], [], [], branch_key=bk)
            sid = dict(claim_ids=[payload_obj.synthesis_id], agent_ids=[payload_obj.combinator_agent_id])
            scope = self._guarded("ledger scope", findings, lambda: self._ledger_scope(payload_obj), [], **sid)
            findings += self._guarded("superseded citations (INT-HANDOFF-014)", findings, lambda: self._cited_superseded(payload_obj), [], **sid)
            findings += self._guarded("claim ledger (INT-LEDGER)", findings, lambda: self._explain_superseded_collisions(check_synthesis_ledger(scope, payload_obj, extra_texts=self._request_texts())), [], **sid)
            conflict_findings, conflict_ids = self._guarded("conflict disclosure (INT-CONFLICT-002)", findings, lambda: self._synthesis_conflicts(payload_obj, scope), ([], []), **sid)
            findings += conflict_findings
            branch_ids += conflict_ids
            ent_findings, ent_ids, checked = self._guarded("synthesis entailment (INT-SYNTH)", findings, lambda: self._synthesis_entailment(payload_obj), ([], [], {}), **sid)
            findings += ent_findings
            branch_ids += ent_ids
            findings = self._state_synthesis_checks(findings, checked)
            findings += self._guarded("unchecked paraphrases (INT-SYNTH-012)", findings, lambda: self._unchecked_paraphrases(payload_obj, scope, checked), [], **sid)
            # The router reads the synthesis, not the reports' receipts: what those receipts left unresolved about the claims
            # the synthesis cites travels with it (the synthesis's own earlier deliveries in full).
            history, carried = self._guarded("relay history (INT-HIST-001)", findings, lambda: self._synthesis_history(payload_obj, findings), ([], []), **sid)
            findings += carried
            if not _is_blocking(findings):
                self.syntheses.setdefault(payload_obj.synthesis_id, payload_obj)
        if isinstance(payload_obj, SpecialistReport):
            return self._finish(msg, "agent_to_agent", findings, [], [], outcomes, branch_ids, structural=structural, branch_formal=branch_formal, branch_key=bk,
                                report=payload_obj, report_named=relayed_named, history=history)
        return self._finish(msg, "agent_to_agent", findings, [], [], outcomes, branch_ids, structural=structural, branch_formal=branch_formal, branch_key=bk, history=history)

    def _revalidate_synthesis(self, synthesis: Synthesis, payload: dict) -> list[IntegrityFinding]:
        """The synthesis delivered to the recipient must re-validate against synthesis/1.0, as a report must against its
        contract (``_revalidate``): a synthesis built around validation (``model_copy(update=...)`` or ``model_construct``,
        with a transformation written as free text, say) is REJECTED here with INT-REQ-009, and a value outside one of
        the contract's closed vocabularies is named (INT-SYNTH-014), instead of reaching the claim ledger, whose rules
        those values select. A synthesis that validated on construction re-validates unchanged, so this adds nothing to
        its receipt."""
        try:
            Synthesis.model_validate(payload)
        except (ValidationError, TypeError, ValueError) as exc:
            sid, cid = _scrub(str(getattr(synthesis, "synthesis_id", "") or ""))[:128], _scrub(str(getattr(synthesis, "combinator_agent_id", "") or ""))[:128]
            out = [IntegrityFinding(code="INT-REQ-009", severity="error",
                                    message=f"synthesis payload does not re-validate against the synthesis contract and is not delivered: {_shape_reason(exc)}",
                                    claim_ids=[sid] if sid else [], agent_ids=[cid] if cid else [])]
            return out + (_vocabulary_findings(payload, exc) if isinstance(exc, ValidationError) else [])
        return []

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

    def _synthesis_history(self, synthesis: Synthesis, findings: list[IntegrityFinding]) -> tuple[list[ReceiptReference], list[IntegrityFinding]]:
        """``(history, carried)`` of a synthesis relay: references to the synthesis's own earlier deliveries and to every
        delivered transmission of the reports it cites (listed, or holding a claim it cites), and INT-HIST-001 for what
        they left unresolved: everything of its own earlier deliveries, and of the reports what names a claim it cites."""
        cited = {cid for sc in synthesis.claims for cid in sc.source_claim_ids} | {cid for e in synthesis.ledger for cid in e.source_claim_ids}
        reports = list(dict.fromkeys(list(synthesis.source_report_ids) + [r.report_id for r in self.transmitted_reports.values() if any(c.claim_id in cited for c in r.claims)]))
        own = self._history_of([("synthesis", synthesis.synthesis_id)])
        sources = self._history_of([("report", rid) for rid in reports])
        carried = self._carried(own, findings, recomputed=True)
        carried += self._carried(sources, findings + carried, claims=cited, layout=False, decided_only=True)
        return own + sources, carried

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
        if isinstance(payload_obj, Synthesis) and payload_obj.combinator_agent_id not in selected:
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
            if msg.contract == "specialist_report/1.0" and msg.recipient_role is AgentRole.ROUTER:  # the delivery a router forward replies to
                self.delivered_to_router.setdefault(rid, []).append(msg.message_id)
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
                    elsewhere = sorted(d for d, t in by_id.items() if d != ref.document_id and locate_quotation(ref.excerpt or "", t.text, document_id=d) is not None)
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
        A quotation credited to another source ("One critic writes that ...") stays unverifiable."""
        from ..adapters.markdown import cited_quotation_spans
        from ..adapters.sources import is_peer_text, nearest_text, quotation_credit, uncredited_excerpt
        if not supplied:
            return []
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
            w = word.strip("'").casefold()
            return any(len(w) >= 4 and (v.startswith(w[:4]) and abs(len(v) - len(w)) <= 3) for v in (x.casefold() for x in re.findall(r"[^\W\d_]+", text)))

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
                    if 0 < len(miss) <= 2 and len(miss) < words and (words >= 3 or all(near_form(w, t.text) for w in miss)) and (not altered or len(miss) < len(missing)):
                        near, missing, altered = d, miss, True
                # The sentence that carries the quotation (a parser may deliver the quotation as its own evidence claim and
                # the sentence that credits it as another claim): the longest claim text holding it, else the response.
                holders = sorted((x.claim_text for x in report.claims if norm(ex) in x.claim_text.casefold()), key=len, reverse=True)
                sentence = holders[0] if holders else c.claim_text
                credit = None
                spans = [sp for sp in cited_quotation_spans(sentence) if norm(sp[2]) == norm(ex)]
                if spans:
                    credit = quotation_credit(sentence, spans[0][0], docs)
                by_kind = credit is not None and credit.generic and bool(own)
                if not (altered or by_kind):
                    continue
                why = (f"{'the request' if near == 'the request' else 'the supplied text ' + near} holds all of its words but {', '.join(missing)} (an altered quotation)" if altered
                       else f"the sentence credits it to {credit.phrase!r}, the text under analysis named by kind (an invented quotation)")
                out.append(IntegrityFinding(code="INT-REQ-003", severity="error",
                                            message=f"quotation '{ex[:120]}' of claim {c.claim_id}, which the report credits to no text, was not found in the supplied texts {doc_ids}: {why}",
                                            claim_ids=[c.claim_id], report_ids=[report.report_id], agent_ids=[report.agent_id], document_ids=doc_ids))
        return out

    @staticmethod
    def _system_check_content(report: SpecialistReport, supplied: list[SuppliedText]) -> list[IntegrityFinding]:
        """INT-REQ-017 (warning): an answer built on a peer specialist's report (a ``peer:`` document among its supplied
        texts) that hands a system check result to the reader as subject content: one of the closed phrases of
        :data:`~.cues.SYSTEM_CHECK_PHRASES` ("a formal check failed ...", "do not copy those two lines") or a finding code,
        outside its quotations. A hub, engine or receipt result is router-side material the student cannot weigh, and it
        may be a false finding (E2E B3). The finding names the claim and quotes its sentence; quoting the peer's own words
        or figures is no such statement."""
        from ..adapters.markdown import find_quotation_spans
        from ..adapters.sources import is_peer_text
        peers = [t for t in supplied if is_peer_text(t)]
        if not peers:
            return []
        out: list[IntegrityFinding] = []
        for c in report.claims:
            text = c.claim_text
            for start, end, _inner in reversed(find_quotation_spans(text)):  # the peer's quoted words are the peer's
                text = text[:start] + " " * (end - start) + text[end:]
            m = _SYSTEM_CHECK_RE.search(text) or _FINDING_CODE_RE.search(text)
            if m is None:
                continue
            sentence = " ".join(c.claim_text.split())
            out.append(IntegrityFinding(code="INT-REQ-017", severity="warning",
                                        message=f"claim {c.claim_id} hands a system check result to the reader as subject content ({' '.join(m.group(0).split())!r} in '{sentence[:220]}'): "
                                                f"the answer builds on the peer report(s) {sorted(t.document_id for t in peers)}, and a hub, engine or receipt result is router-side material "
                                                "the student cannot weigh and may be a false finding; the answer should state the subject point, not the check",
                                        claim_ids=[c.claim_id], report_ids=[report.report_id], agent_ids=[report.agent_id], document_ids=sorted(t.document_id for t in peers)))
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
        from ..adapters.markdown import find_quotation_spans
        from ..adapters.sources import credited_spans
        from ..integrity.ledger import credited_date_repairings, figure_spellings
        from ..adapters.sources import is_peer_text
        peers = [t for t in supplied if is_peer_text(t)]
        if not peers:
            return []
        known: set[str] = set()
        for t in supplied:
            for _label, keys in figure_spellings(t.text):
                known |= keys
        out: list[IntegrityFinding] = []
        for c in _material_claims(report):
            text = c.claim_text
            for start, end, _inner in reversed(find_quotation_spans(text)):  # quotations are checked as quotations
                text = text[:start] + " " * (end - start) + text[end:]
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
        from ..adapters.markdown import cited_quotation_spans
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
            for start, _end, inner in cited_quotation_spans(c.claim_text):
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
        from ..adapters.markdown import cited_quotation_spans
        out: list[IntegrityFinding] = []
        for issue in report.unresolved_issues:
            m = _FOLDED_TAIL_RE.search(issue)
            if m is None:
                continue
            tail_id = m.group("tail")
            head_text = " ".join(c.claim_text for c in report.claims if c.claim_id != tail_id)
            cited = {(ref.excerpt or "").strip() for c in report.claims if c.claim_id != tail_id for ref in c.source_refs}
            quotes = _dedupe_ids(inner.strip() for _s, _e, inner in cited_quotation_spans(report.original_response)
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
        if material and answer_words == 0:
            answer_words = _wrapped_answer_words(report, material, view)
        if material and answer_words == 0 and view is None:
            # a branch with no word-count view of its own (Economics, Geography, Business, Psychology): a worked calculation of the
            # answer ('12 500 + 7 500 = 20 000') is its answer proper, one word per calculation, as a STEM branch's view counts a
            # maths span (repair round 4, rerun-stem-precision-11)
            answer_words = _worked_calculations(report.original_response)
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
        from ..adapters.markdown import cited_quotation_spans
        resp_tokens = [light_stem(t) for t in _tokens(report.original_response)]
        ask_tokens = [light_stem(t) for t in _tokens(req.user_input)]
        if not resp_tokens or not ask_tokens:
            return None
        if _writes_own_arithmetic(report.original_response, req.user_input):
            return None  # the response computes ('$5.00 − $3.00 = $2.00'), which no restatement of the request does
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
                echoed_quotes = [inner for _s, _e, inner in cited_quotation_spans(report.original_response)
                                 if _tokens(inner) and set(light_stem(t) for t in _tokens(inner)) <= ask_set and not any(_located(inner, t.text, t.document_id) for t in supplied)]
                if echoed_quotes:
                    how = (f"{overlap:.0%} of its distinct words (content light stems; function words aside) occur in the request, it is {ratio:.2f}x the request's length (no longer than {_ECHO_QUOTED_LENGTH_RATIO}x), "
                           f"and it quotes the request's own words as if they were the text's ({[q[:60] for q in echoed_quotes[:_MAX_NAMED]]} occur in the request and in no supplied text)")
        if how is None:
            return None
        return IntegrityFinding(code="INT-REQ-011", severity="error", message=f"the response restates the request instead of answering it ({how}); no request item counts as addressed", claim_ids=[c.claim_id for c in report.claims], report_ids=[report.report_id], agent_ids=[report.agent_id])

    def _coverage(self, req: TaskRequest, report: SpecialistReport, *, echoed: bool = False, hooks=None, profile_key: str = "",
                  no_answer: bool = False) -> list[CoverageRecord]:
        """Which request items the report addresses (a note never addresses one). A lettered or numbered item ("(b) Describe
        ...", "1. ¿Cómo era ...?") is compared per part when the answer labels its parts with the request's labels: the
        claims under the same label address it, so a reply that answers part (a) alone leaves (b) to (d) unaddressed
        whatever words they share, and "1. Basura y cristales rotos." addresses item 1 in any language. Otherwise the
        lexical heuristic: enough shared content terms with one material claim, or with the material claims of one
        paragraph together (a paragraph that answers a guiding question need not repeat its words in one sentence); a
        guiding, essay or research question is answered by a point, thesis or judgement claim that takes up its terms.
        The shared terms must include one of the item's own topic terms whenever it has any: an item's command words and
        the instructions on the form of its answer (:data:`_COMMAND_STEMS`) are no evidence on their own, so "2 + 2 = 4"
        addresses no "Calculate the acceleration", and one irrelevant sum addresses none of three such items.
        ``hooks`` (a branch's hub hooks; the STEM branches) lend each claim extra words (STEM: the dimensions, units and
        symbols of its quantities), read wherever the claim's own words are; their ``topic_evidence`` may stand in for a
        shared topic term (a symbol the item asks for, the item's own figures), and an item whose words are all command
        words but which names what it asks for in notation (``names_notation``: "Solve 3x + 5 = 20") is addressed only
        by a claim that evidence finds about that notation. A claim that is a table row offers the word "table", so a table
        answers "Construct the table". A request with exactly one required item (and an answer with a material claim, no
        restatement and an answer proper, ``no_answer`` False) has no other item a claim could be answering: when the lexical
        test finds no claim, every material claim that shares one topic word with the request (its item, or the context the
        request gives it: the words of the request text beyond the command and form words, :data:`_COMMAND_STEMS`) addresses
        it. An answer that touches nothing the request names still addresses nothing ("2 + 2 = 4" to "Calculate the
        acceleration.")."""
        out: list[CoverageRecord] = []
        material = _material_claims(report)
        sections = _answer_sections(report.original_response)
        section_of = _claim_sections(report.original_response, sections, material) if sections else {}
        answer_labels = {lab for _start, labels in sections for lab in labels}
        item_labels = {part_label(i.text) for i in req.items} - {None}
        by_part = bool(item_labels & answer_labels)  # the answer labels its parts as the request does
        claim_terms: dict[str, set[str]] = {}
        for c in material:
            terms = _terms(c.claim_text)
            if _TABLE_CLAIM_RE.match(c.claim_text):  # a table row answers an item that asks for a table
                terms = terms | {light_stem("table")}
            if hooks is not None:  # the branch's extra words for this claim (STEM: the dimensions of its quantities)
                extra = self._hook(lambda: hooks.coverage_terms(c.claim_text, report.original_response, req.user_input, profile_key), frozenset())
                terms = terms | _terms(" ".join(sorted(extra)))
            claim_terms[c.claim_id] = terms
        single = [i for i in req.items if i.required]
        single_item = single[0].item_id if len(single) == 1 and not echoed and not no_answer and material else None
        request_topic = (_terms(_ITEM_LABEL_RE.sub("", req.user_input)) - _COMMAND_STEMS - _NOT_TOPIC_STEMS) if single_item else set()
        groups: dict[str, set[str]] = {}
        members: dict[str, list[ClaimRecord]] = {}
        for c in material:
            groups.setdefault(_paragraph_key(c.claim_id), set()).update(claim_terms[c.claim_id])
            members.setdefault(_paragraph_key(c.claim_id), []).append(c)
        for item in req.items:
            if echoed:  # a restated request addresses nothing, whatever words it shares with the items
                out.append(CoverageRecord(item_id=item.item_id, addressed=False, addressed_by_claim_ids=[], method="lexical_heuristic"))
                continue
            lab = part_label(item.text)
            if by_part and lab is not None:
                hits = [c.claim_id for c in material if lab in section_of.get(c.claim_id, ())]
                out.append(CoverageRecord(item_id=item.item_id, addressed=bool(hits), addressed_by_claim_ids=hits, method="part_label"))
                continue
            it = _terms(_MARK_ANNOTATION_RE.sub(" ", _ITEM_LABEL_RE.sub("", item.text)))  # "[2 marks]" is the item's furniture, no topic
            need = max(1, min(2, len(it) // 3))
            # the item's topic: what it names beyond its command words and the form of the answer (S3), in words or, for an
            # item with no such word, in notation the branch reads ("Solve 3x + 5 = 20")
            topic = it - _COMMAND_STEMS
            notation = not topic and bool(it) and self._names_notation(hooks, item.text, profile_key)
            evidence = self._topic_evidence(hooks, item.text, report, req, profile_key, notation) if topic or notation else (lambda _c: False)

            def addresses(terms: set[str], claims: list[ClaimRecord], at_least: int = need) -> bool:
                """Enough shared terms, one of them a topic term of the item, or the branch's evidence that one of the
                claims is about the item (STEM: it computes a symbol the item asks for, or with the item's own figures);
                an item that names nothing beyond its command words and no notation needs no topic term. The branch's
                evidence also stands in for the shared terms themselves: a claim that computes the very symbol or with
                the very figures the item names is about it however few words it writes ("pH = −log₁₀(0.0025) = 2.60"
                for "Calculate the pH ...", "N = 10 + 6 + 4 = 20" for an item giving 10, 6 and 4: repair round 2,
                holdout2 coverage class); unrelated arithmetic has no such evidence ("2 + 2 = 4", STEM review S3)."""
                shared = it & terms
                if len(shared) < at_least:
                    return bool(topic or notation) and any(evidence(x) for x in claims)
                return (not topic and not notation) or bool(shared & topic) or any(evidence(x) for x in claims)
            hits = [c.claim_id for c in material if it and addresses(claim_terms[c.claim_id], [c])]  # a note never addresses an item
            if it and not hits:  # a paragraph's claims together
                hits = [c.claim_id for c in material if addresses(groups.get(_paragraph_key(c.claim_id), set()), members.get(_paragraph_key(c.claim_id), []))]
            if it and not hits and _ITEM_LABEL_RE.match(item.text):
                # A guiding (essay, research) question frames the whole answer: a point, thesis or judgement claim that
                # takes up its terms answers it, even when no sentence repeats enough of its words.
                hits = [c.claim_id for c in material if c.claim_role in ("point", "thesis", "judgement") and addresses(claim_terms[c.claim_id], [c], 1)]
            if it and not hits and item.item_id == single_item and request_topic:
                # The request's only item: the lexical threshold tells items apart, and there is no other item to tell it from,
                # so a material claim that takes up one word the request names addresses it (B18; c03-dich, c04-quote, i02c)
                hits = [c.claim_id for c in material if claim_terms[c.claim_id] & request_topic]
            out.append(CoverageRecord(item_id=item.item_id, addressed=bool(hits) or not it, addressed_by_claim_ids=hits, method="lexical_heuristic"))
        return out

    def _topic_evidence(self, hooks, item_text: str, report: SpecialistReport, req: TaskRequest, profile_key: str,
                        notation: bool = False) -> Callable[[ClaimRecord], bool]:
        """Per claim, the branch hooks' evidence that the claim is about the item beyond the words they share
        (``topic_evidence``; the STEM branches: a symbol the item asks for, the item's own figures; with ``notation``, for
        an item that names what it asks for in notation only), memoised for the item; always False without such a hook,
        and False when the hook fails (it only refines a heuristic, so a failure never addresses an item)."""
        fn = getattr(hooks, "topic_evidence", None) if hooks is not None else None
        if fn is None:
            return lambda _c: False
        memo: dict[str, bool] = {}
        extra = {"notation_only": True} if notation else {}

        def evidence(c: ClaimRecord) -> bool:
            if c.claim_id not in memo:
                memo[c.claim_id] = self._hook(lambda: bool(fn(item_text, c.claim_text, report.original_response, req.user_input, profile_key, **extra)), False)
            return memo[c.claim_id]
        return evidence

    def _names_notation(self, hooks, item_text: str, profile_key: str) -> bool:
        """Whether the branch hooks read the item as naming what it asks for in notation (``names_notation``; the STEM
        branches: "Solve 3x + 5 = 20", "Simplify √50"); False without such a hook or when it fails (the item then needs
        no topic term, as before)."""
        fn = getattr(hooks, "names_notation", None) if hooks is not None else None
        if fn is None:
            return False
        return self._hook(lambda: bool(fn(item_text, profile_key)), False)

    def _constraints(self, req: TaskRequest, report: SpecialistReport, view=None) -> tuple[list[ConstraintResult], list[str]]:
        """Every request constraint decided on the report: word and paragraph bounds as signed engine results, the citing
        constraint deterministically. A word bound is measured on its scope (``Constraint.scope``, E2E B4): the whole answer;
        the answer's sections of the listed parts together (``part``) or each on its own (``each_part``, one problem over
        every part); or the paragraph or answer proper the request asks for, without a plan, meta-text and side answers
        (``deliverable_blocks``). A part the answer does not label is never measured on another span: for a maximum, a
        whole answer within the bound proves the part is (the part is in it); for a minimum, a whole answer below it proves
        the part is; otherwise the bound is not checkable on its scope and the receipt says so (INT-REQ-005 warning)."""
        results: list[ConstraintResult] = []
        formal_ids: list[str] = []
        cache: dict[tuple, tuple[int, int, int]] = {}
        text = report.original_response

        def words_of(span: Optional[str], excludes: tuple[str, ...], key) -> tuple[int, int, int]:
            if (key, excludes) not in cache:
                cache[(key, excludes)] = measure_answer_words(text if span is None else span, excludes=excludes, view=view)
            return cache[(key, excludes)]

        def measure(c: Constraint) -> dict:
            """{"kind": whole | scoped | parts | unlocated, "words", "notes", "exempt", "parts": [(label, words)], "missing": [...], "where": str}"""
            ex = tuple(sorted(c.excludes))
            whole = words_of(None, ex, "whole")
            scope = c.scope
            if scope is None or scope.kind == "whole":
                return {"kind": "whole", "words": whole[0], "notes": whole[1], "exempt": whole[2], "where": ""}
            if scope.kind in ("paragraph", "answer_proper"):
                blocks = deliverable_blocks(text, req.user_input)
                span = "\n\n".join(blocks)
                w = words_of(span, ex, ("deliverable",))
                what = "the paragraph the request asks for" if scope.kind == "paragraph" else "the answer proper"
                return {"kind": "scoped", "words": w[0], "notes": w[1] + max(0, whole[0] - w[0]), "exempt": w[2],
                        "where": f" on {what} ({len(blocks)} block(s); a plan, meta-text and side answers to the student's other questions left out: {max(0, whole[0] - w[0])} words)"}
            located = [(lab, part_section_text(text, lab)) for lab in scope.parts]
            missing = [lab for lab, span in located if span is None]
            if missing:
                return {"kind": "unlocated", "words": whole[0], "notes": whole[1], "exempt": whole[2], "missing": missing,
                        "where": f" (the answer labels no section ({') or ('.join(missing)})" + ")"}
            if scope.kind == "each_part":
                per = [(lab, words_of(span, ex, ("part", lab))[0]) for lab, span in located]
                return {"kind": "parts", "words": max(n for _lab, n in per), "notes": 0, "exempt": 0, "parts": per,
                        "where": " on each part: " + ", ".join(f"({lab}) {n}" for lab, n in per) + " words (each part's own section, its label left out)"}
            span = "\n\n".join(sp for _lab, sp in located)
            w = words_of(span, ex, ("parts", tuple(scope.parts)))
            labels = " and ".join(f"({lab})" for lab in scope.parts)
            return {"kind": "scoped", "words": w[0], "notes": w[1], "exempt": w[2], "where": f" on part {labels} (the answer's own section, its label left out)"}

        paras = count_paragraphs(text)
        # A minimum and a maximum stated by one span ("about 250 words", "between 300 and 400 words", "exactly 3
        # paragraphs") are decided by ONE range problem when the measurement lies within both: each constraint cites that
        # signed result. Only a measurement outside the range is decided side by side, to say which bound it crosses.
        ranged: dict[str, VerificationResult] = {}
        for unit in ("words", "paragraphs"):
            spans: dict[tuple, dict[str, Constraint]] = {}
            for c in req.constraints:
                if c.kind in (f"min_{unit}", f"max_{unit}") and c.value is not None:
                    spans.setdefault((c.text, c.scope.model_dump_json() if c.scope is not None else None), {})[c.kind[:3]] = c
            for pair in spans.values():
                first = next(iter(pair.values()))
                m = measure(first) if unit == "words" else {"kind": "whole", "words": paras}
                if m["kind"] not in ("whole", "scoped"):
                    continue
                measured = m["words"]
                if "min" in pair and "max" in pair and pair["min"].value.isdecimal() and pair["max"].value.isdecimal() and int(pair["min"].value) <= measured <= int(pair["max"].value):
                    res = self._formal_range(req, pair["min"], pair["max"], measured)  # the engine decides; the comparison only chooses the problem
                    if res.status is S.ENTAILED:
                        ranged[pair["min"].constraint_id] = ranged[pair["max"].constraint_id] = res
        for c in req.constraints:
            if c.kind in ("max_words", "min_words", "max_paragraphs", "min_paragraphs") and c.value is not None:
                is_words = c.kind.endswith("words")
                m = measure(c) if is_words else {"kind": "whole", "words": paras, "notes": 0, "exempt": 0, "where": ""}
                unit = "words" if is_words else "paragraphs"
                if m["kind"] == "unlocated":
                    # never measured on another span: the whole answer decides only what it proves about the part
                    whole_ok = c.value.isdecimal() and ((m["words"] <= int(c.value)) if c.kind == "max_words" else (m["words"] < int(c.value)))
                    if not whole_ok:
                        results.append(ConstraintResult(constraint_id=c.constraint_id, satisfied=None, method="not_checkable",
                                                        detail=f"bound {c.kind} {c.value} on part ({') ('.join(c.scope.parts)}){m['where']}: it cannot be measured on its scope, and the whole answer ({m['words']} words) does not decide it"))
                        continue
                    res = self._formal_bound(req, c, m["words"])
                    detail = (f"measured {m['words']} words on the whole answer{m['where']}: the part is within the whole, so the whole decides the bound; bound {c.kind} {c.value}; solver {res.status.value}")
                elif m["kind"] == "parts":
                    res = self._formal_parts(req, c, m["parts"])
                    detail = f"measured{m['where']}; bound {c.kind} {c.value} each; solver {res.status.value}"
                else:
                    res = ranged.get(c.constraint_id) or self._formal_bound(req, c, m["words"])
                    excluded = f" ({m['notes']} words of note or meta-text blocks excluded, as for paragraphs)" if is_words and m["notes"] and m["kind"] == "whole" else ""
                    if is_words and c.excludes:
                        excluded += f" (prose only: {m['exempt']} words of {' and '.join(c.excludes)} excluded, as the request sets them outside the bound)"
                    detail = f"measured {m['words']} {unit}{m['where']}{excluded}; bound {c.kind} {c.value}; solver {res.status.value}"
                if res.result_id not in formal_ids:
                    formal_ids.append(res.result_id)
                sat = True if res.status is S.ENTAILED else False if res.status is S.COUNTEREXAMPLE else None
                results.append(ConstraintResult(constraint_id=c.constraint_id, satisfied=sat, method="formal", detail=truncate(detail, _DETAIL_MAX),
                                                formal_result_id=res.result_id, formal_status=res.status.value))
            elif c.kind == "must_cite_supplied_text":
                cited = any(cl.source_refs for cl in report.claims)
                results.append(ConstraintResult(constraint_id=c.constraint_id, satisfied=cited, method="deterministic", detail="at least one claim carries a source reference" if cited else "no claim carries a source reference"))
            else:
                results.append(ConstraintResult(constraint_id=c.constraint_id, satisfied=None, method="not_checkable", detail="constraint kind not checkable by code"))
        return results, formal_ids

    def _formal_parts(self, req: TaskRequest, c: Constraint, parts: list[tuple[str, int]]) -> VerificationResult:
        """Encode 'every listed part's measured count <op> bound' as ONE IR entailment over one symbol per part (a signed,
        bound result the constraint cites)."""
        op = {"max_words": "le", "min_words": "ge"}[c.kind]
        names = [f"n_{re.sub(r'[^a-z0-9]', '', lab.casefold()) or 'x'}_{k}" for k, (lab, _n) in enumerate(parts)]
        problem = {
            "problem_id": f"constraint-{c.constraint_id}-{uuid.uuid4().hex[:8]}", "request_id": req.request_id, "claim_id": f"constraint:{c.constraint_id}", "query": "entailment",
            "symbols": [{"name": n, "sort": "Int", "meaning": f"measured words of part ({lab}) for {c.kind}", "grounding": {"kind": "supplied_text", "verified": True}} for n, (lab, _m) in zip(names, parts)],
            "premises": [{"id": f"MEASURED_{k}", "expr": {"op": "eq", "left": {"op": "var", "name": n}, "right": {"op": "int", "value": str(m)}}, "label": f"part ({lab}) has {m}", "grounding": {"kind": "supplied_text", "verified": True}}
                         for k, (n, (lab, m)) in enumerate(zip(names, parts))],
            "conclusion": {"id": "BOUND", "expr": {"op": "and", "args": [{"op": op, "left": {"op": "var", "name": n}, "right": {"op": "int", "value": c.value}} for n in names]} if len(names) > 1 else
                           {"op": op, "left": {"op": "var", "name": names[0]}, "right": {"op": "int", "value": c.value}}, "label": c.text, "grounding": {"kind": "task_setting", "verified": True}},
        }
        return self._decide_bound(problem)

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
        return self._decide_bound({
            "problem_id": f"constraint-{c.constraint_id}-{uuid.uuid4().hex[:8]}", "request_id": req.request_id, "claim_id": f"constraint:{c.constraint_id}", "query": "entailment",
            "symbols": [{"name": "n", "sort": "Int", "meaning": f"measured count for {c.kind}", "grounding": {"kind": "supplied_text", "verified": True}}],
            "premises": [{"id": "MEASURED", "expr": {"op": "eq", "left": {"op": "var", "name": "n"}, "right": {"op": "int", "value": str(measured)}}, "label": f"response has {measured}", "grounding": {"kind": "supplied_text", "verified": True}}],
            "conclusion": {"id": "BOUND", "expr": {"op": op, "left": {"op": "var", "name": "n"}, "right": {"op": "int", "value": c.value}}, "label": c.text, "grounding": {"kind": "task_setting", "verified": True}},
        })

    def _decide_bound(self, problem: dict) -> VerificationResult:
        """Validate a code-built bound problem (one count, or one count per part) and decide it: a signed, bound result."""
        return verify(Problem.model_validate(problem), self.config, signing_key=self.key, key_id=self.key_id, diagnose=False)  # a code-built check

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
            if out is None:
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
            if out.verification is not None and out.verification.status is S.INCONSISTENT_PREMISES:
                untrusted = self._untrusted_result(out)
                if untrusted is None:
                    findings.append(self._inconsistent_premises(c, out))
                else:  # evidence the composer refused (signature, binding, staleness) charges nobody
                    findings.append(IntegrityFinding(code="INT-REQ-006", severity="warning",
                                                     message=f"the engine result for claim {c.claim_id} reports premises that contradict each other, but it is not trusted ({untrusted}; displayed {out.display_status.value}): nothing is charged to the specialist, and the claim was not checked",
                                                     claim_ids=[c.claim_id], related_result_ids=[out.verification.result_id], deterministic=True))
        if contributed and len(self.formalized) >= 2:  # only a report that formalized something can be party to a conflict
            try:
                res, f = check_cross_report_consistency(list(self.formalized.values()), request_id=self.plan.request_id, config=self.config, signing_key=self.key, assumed_readings=frozenset(self.ambiguous_pooled))
            except Exception as exc:  # the outcomes above are kept; the router is told the joint check is missing
                findings.append(IntegrityFinding(code="INT-INTERNAL-001", severity="error", message=f"the channel's cross-agent consistency check failed internally ({type(exc).__name__}); contradictions with other agents' claims were not checked on this receipt",
                                                 report_ids=[report.report_id], agent_ids=[report.agent_id]))
                return outcomes
            f = self._with_report_ids(f)
            findings.extend(f)
            self.conflicts_seen.extend((frozenset(x.claim_ids), x.formal_result_id) for x in f if x.code == "INT-CONFLICT-001")
        return outcomes

    def _untrusted_result(self, out: ClaimVerificationOutcome) -> Optional[str]:
        """Why the engine result of ``out`` is not evidence the channel may charge a specialist with, or None when it is: the
        composer displays the engine's status only for a result it trusts (bound, current, signed under its key), so a
        TRANSLATED claim's result is trusted exactly when it is displayed; an AMBIGUOUS_TRANSLATION's result (verified on the
        assumed reading, displayed as ambiguous) must bind to the translated problem, be current and carry a signature that
        verifies under the channel's key."""
        from ..translate.outcome import _binding_problem
        if out.verification is None:
            return "no engine result"
        if out.translation.status is TranslationStatus.TRANSLATED:
            return None if out.display_status is out.verification.status else f"the outcome composer rejected it and displays {out.display_status.value}"
        if out.translation.status is TranslationStatus.AMBIGUOUS_TRANSLATION:
            return _binding_problem(out.translation, out.verification, self.key)
        return f"its translation is {out.translation.status.value}"

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
        outcomes = list(outcomes or ())
        info = {"overflow": overflow, "report_incomplete": list(diagnosis.incomplete),
                "claims_incomplete": sum(1 for o in outcomes if o.diagnosis_incomplete),
                "engine_undiagnosed": sum(1 for o in outcomes if o.verification is not None and rules_state(o.verification.argument_rules)[0] != "complete")}
        return items[:MAX_PER_RECEIPT], arg, info

    def _encoding_disagreements(self, outcomes, branch_formal, findings) -> list[IntegrityFinding]:
        """INT-XENC-001 (warning, B20): a claim carries both a branch formal check of one of its own statements (the check's
        ``claim_ids`` name it) and a translation the engine decided, and the two definitive answers are opposite: the check
        fails (a clause the claim states does not hold) while the translation's display is a positive verdict (ENTAILED,
        CONSISTENT, SATISFIABLE) on the claim as a whole. A claim one of whose clauses is false cannot follow, so at least one
        of the two encodings misreads the claim (the check its clause, or the translation the claim, dropping or changing
        that clause), and the channel cannot tell which. The converse is no disagreement: a check that holds covers one
        clause, and the claim may still fail on another clause or on a link the check does not read (a negative verdict
        there stays a negative verdict). Only a translation result the composer trusts (a TRANSLATED claim displayed with
        the engine's own status) and a decided check with a signed result are compared; both verdicts stay on the receipt
        as they are (the check's INT-SUBJ-001 is never demoted), and the finding names both result ids. One finding per
        claim and check pair; an existing one (a relayed report checked again) is not repeated."""
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
                report: Optional[SpecialistReport] = None, report_named=None, history=()) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        structural = [self._labelled(sf) for sf in structural]
        findings = [self._labelled(f) for f in findings]
        try:  # B20: two encodings of one claim that disagree are named; neither verdict is demoted or dropped
            findings = findings + self._encoding_disagreements(outcomes, branch_formal, findings)
        except Exception as exc:  # the comparison only adds; its failure is named, never raised
            findings.append(IntegrityFinding(code="INT-INTERNAL-001", severity="error", message=f"the channel's encoding comparison (INT-XENC-001) check failed internally ({type(exc).__name__}); its findings are missing from this receipt and must not be read as a pass"))
        named, arg_findings, named_info = self._argument_diagnosis(findings, structural, outcomes, report, report_named)
        findings = findings + arg_findings
        branch_key = branch_key or self.branch.key
        blocking = _is_blocking(findings)
        subject_flag = any(sf.severity in ("error", "warning") for sf in structural)
        if not blocking:
            self._record_delivery(msg)
        if blocking:
            status = TransmissionStatus.REJECTED
        elif findings or subject_flag or any(_no_result(o) for o in outcomes):
            # a claim whose engine gave no verdict, whose encoding is no verdict on it (vacuous, circular, no valid encoding)
            # or whose result the composer refused is never delivered as a clean acceptance
            status = TransmissionStatus.ACCEPTED_WITH_FINDINGS
        else:
            status = TransmissionStatus.ACCEPTED
        ids = list(formal_ids) + [o.verification.result_id for o in outcomes if o.verification is not None] + [f.formal_result_id for f in findings if f.formal_result_id]
        receipt = self._receipt(msg.message_id, direction, status, findings, coverage=coverage, constraint_results=constraint_results, outcomes=outcomes,
                                formal_ids=sorted(set(ids)), structural=structural, branch_formal=branch_formal, branch_key=branch_key, named=named, history=history,
                                summary=self._summary_response(status, findings, coverage, constraint_results, outcomes, structural, branch_formal, branch_key, history,
                                                               named=named, named_info=named_info))
        key = self._payload_key(msg)
        if not blocking and key is not None:  # a delivered transmission of a report or synthesis: part of its history from now on
            self.payload_history.setdefault(key, []).append(receipt.receipt_id)
        return (msg if status is not TransmissionStatus.REJECTED else None), receipt

    def _receipt(self, message_id: str, direction: str, status: TransmissionStatus, findings, *, coverage=(), constraint_results=(), outcomes=(), formal_ids=(), structural=(), branch_formal=(), summary: str, branch_key: Optional[str] = None,
                 named=(), history=()) -> TransmissionReceipt:
        r = TransmissionReceipt(receipt_id=uuid.uuid4().hex, message_id=message_id, request_id=self.plan.request_id, task_id=self.plan.task_id, direction=direction,
                                status=status, findings=list(findings), coverage=list(coverage), constraint_results=list(constraint_results), outcomes=list(outcomes),
                                branch=branch_key or self.branch.key, structural_findings=list(structural), formal_checks=list(branch_formal),
                                formal_result_ids=list(formal_ids), history=list(history), summary=_fit_summary(summary), created_at=_now(), named_diagnostics=list(named))
        self.receipts.append(r)
        self._receipt_index[r.receipt_id] = r
        return r

    # ------------------------------------------------------------------ relay history
    @staticmethod
    def _payload_key(msg: AgentMessage) -> Optional[tuple[str, str]]:
        """``("report", report id)`` or ``("synthesis", synthesis id)`` of a message that carries one, else None."""
        if not isinstance(msg.payload, dict):
            return None
        if msg.contract.startswith("specialist_report"):
            rid = msg.payload.get("report_id")
            return ("report", rid) if isinstance(rid, str) and rid else None
        if msg.contract.startswith("synthesis"):
            sid = msg.payload.get("synthesis_id")
            return ("synthesis", sid) if isinstance(sid, str) and sid else None
        return None

    @staticmethod
    def _reference(receipt: TransmissionReceipt, kind: str, pid: str) -> ReceiptReference:
        """The reference to an earlier receipt with what it left unresolved: its own error and warning findings (never the
        findings it carried itself: they are referenced at their own receipt), its subject findings of warning or error
        severity, its branch formal checks that failed or stayed undecided and its request constraints that failed."""
        return ReceiptReference(receipt_id=receipt.receipt_id, message_id=receipt.message_id, direction=receipt.direction, status=receipt.status,
                                payload_kind=kind, payload_id=pid,
                                unresolved_findings=[f for f in receipt.findings if f.severity in ("error", "warning") and f.code != _HISTORY_CODE],
                                unresolved_subject_findings=[sf for sf in receipt.structural_findings if sf.severity in ("error", "warning")],
                                unresolved_checks=[c for c in receipt.formal_checks if c.satisfied is not True] + [c for c in receipt.constraint_results if c.satisfied is False])

    def _history_of(self, keys: list[tuple[str, str]]) -> list[ReceiptReference]:
        """References to every delivered transmission of the given reports and syntheses on this channel, in delivery
        order per payload (at most :data:`_MAX_HISTORY`; the first, a report's arrival, is always kept)."""
        refs: list[ReceiptReference] = []
        seen: set[str] = set()
        for kind, pid in dict.fromkeys(keys):
            for rid in self.payload_history.get((kind, pid), ()):
                receipt = self._receipt_index.get(rid)
                if receipt is None or rid in seen:
                    continue
                seen.add(rid)
                refs.append(self._reference(receipt, kind, pid))
        if len(refs) > _MAX_HISTORY:
            refs = refs[:1] + refs[-(_MAX_HISTORY - 1):]
        return refs

    @staticmethod
    def _carried(refs: list[ReceiptReference], own: list[IntegrityFinding], own_structural=(), claims: Optional[set[str]] = None,
                 recomputed: bool = False, layout: bool = True, decided_only: bool = False) -> list[IntegrityFinding]:
        """INT-HIST-001, with the original severity, for every unresolved finding and subject finding of the referenced
        receipts that this receipt does not state again itself (same code, claims and message; a subject finding: same
        code and claims), each named once, keeping its claims, reports, agents, documents and signed result. With
        ``claims`` only those naming one of these claims are carried (a synthesis carries what concerns the claims it
        cites; the rest stays in the history it references). With ``recomputed`` (an earlier delivery of the same
        synthesis, whose checks this receipt runs again) a finding of the same code on the same claims is stated again,
        whatever its wording. With ``layout`` False a subject finding about the report's paragraphs or sentence style
        (:data:`_LAYOUT_PREFIXES`) is not carried: a synthesis restates the claims it cites, never the report's paragraphs,
        so such a finding stays in the history it references (close round 2, DIFF-05). With ``decided_only`` (a forward or
        relay to a peer specialist, and what a synthesis carries from the reports it cites: accuracy round 1, DV2-05) only the
        errors, the warnings that state a fault the content was found to have (:data:`_DECIDED_WARNINGS`) and the subject
        findings at error or naming a STEM defect (:data:`_DECIDED_SUBJECT_WARNINGS`) are carried; every other warning stays
        in the history the receipt references."""
        mine = {(f.code, tuple(sorted(f.claim_ids)), "" if recomputed else f.message) for f in own}
        mine_sf = {(sf.code, tuple(sorted(sf.claim_ids))) for sf in own_structural}
        out: list[IntegrityFinding] = []
        codes: list[str] = []  # the original code of each carried finding, in order
        seen: set[tuple] = set()
        for ref in refs:
            for f in ref.unresolved_findings:
                key = (f.code, tuple(sorted(f.claim_ids)), f.message)
                if (key[:2] + (("" if recomputed else f.message),)) in mine or key in seen or (claims is not None and not set(f.claim_ids) & claims):
                    continue
                if decided_only and f.severity != "error" and f.code not in _DECIDED_WARNINGS:
                    continue
                seen.add(key)
                codes.append(f.code)
                out.append(carried_finding(ref, f))  # the one constructor the response gate re-makes it with (repair round 3, ADV3-02)
            for sf in ref.unresolved_subject_findings:
                key = ("subject", sf.code, tuple(sorted(sf.claim_ids)))
                if key[1:] in mine_sf or key in seen or (claims is not None and not set(sf.claim_ids) & claims):
                    continue
                if not layout and sf.code.startswith(_LAYOUT_PREFIXES):
                    continue
                if decided_only and sf.severity != "error" and sf.code not in _DECIDED_SUBJECT_WARNINGS:
                    continue
                seen.add(key)
                codes.append(sf.code)
                out.append(carried_subject_finding(ref, sf))
        if len(out) > _MAX_CARRIED:
            rest, rest_codes = out[_MAX_CARRIED - 1:], codes[_MAX_CARRIED - 1:]
            out = out[:_MAX_CARRIED - 1] + [IntegrityFinding(code=_HISTORY_CODE, severity="error" if any(f.severity == "error" for f in rest) else "warning",
                                                             message=f"and {len(rest)} more unresolved findings of earlier receipts ({', '.join(sorted(set(rest_codes))[:8])}), listed in this receipt's history",
                                                             claim_ids=_dedupe_ids(cid for f in rest for cid in f.claim_ids)[:64], message_ids=_dedupe_ids(m for f in rest for m in f.message_ids)[:64])]
        return out

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
    def _summary_response(status, findings, coverage, constraint_results, outcomes, structural=(), branch_formal=(), branch="generic", history=(), *, named=(), named_info=None) -> str:
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
        blank = [o.claim_id for o in outcomes if _no_result(o)]
        noverdict = (f"No verdict a clean receipt could stand on for claim(s) {_named(blank)} (engine non-result, invalid or vacuous "
                     f"encoding, an ambiguous or unsupported translation, or a result the composer refused; see each claim's display). ") if blank else ""
        subject = ", ".join(f"{code} x{n}" for code, n in sorted(histogram.items())) or "none"
        earlier = ""
        if history:
            open_refs = [h.receipt_id for h in history if h.unresolved]
            carried = sum(1 for f in findings if f.code == _HISTORY_CODE)
            earlier = (f"History: {len(history)} earlier receipt(s) of what this transmission carries, {len(open_refs)} with unresolved findings"
                       + (f" ({_named(open_refs)}); {carried} carried as {_HISTORY_CODE}" if open_refs else "") + ". ")
        return (f"Transmission {status.value} via branch {branch}. Items addressed (heuristic): {covered}/{len(coverage)}. Request constraints: "
                + (", ".join(f"{c.constraint_id}={'ok' if c.satisfied else 'FAILED' if c.satisfied is False else 'unchecked'}" for c in constraint_results) or "none")
                + f". Report's own formal checks: {bf}. Subject findings: {subject}. Claim outcomes: {verdicts or 'none'}. " + noverdict + earlier
                + f"Findings: {', '.join(sorted({f.code for f in findings})) or 'none'}. " + TranslatorChannel._argument_summary(named, named_info) + _SCOPE_TAIL)
