#!/usr/bin/env python3
"""Arena driver: feed real specialist-agent outputs through the hub and measure.

Inputs (one round directory):
  <round>/specialists/*.json   {task_id, subject, agent_id, task_type?, question, supplied_texts:[{document_id,title?,author?,text}], response_text}
  <round>/translations/*.json  optional: {report_id, claims: {claim_id: <translator JSON object>}, claim_text_sha256?: {claim_id: sha256}}
                               The optional claim_text_sha256 map (list_claims.py --json prints the digest of every claim) binds each
                               fixture to the claim text it was produced for; without it the harness captures the digest of each
                               fixture's claim from the genuine transmission. Either way the fixture provider refuses to serve a
                               fixture for a claim whose text changed (a mutation that alters the sentence, ids that shift when a
                               sentence is prepended), and the channel independently rejects an outcome bound to another text
                               (INT-STALE-011). Such a refusal is recorded per claim as STALE_FIXTURE_REFUSED: no verdict, and not an
                               infrastructure error.
  <round>/syntheses/*.json     optional: {report_id, claims:[{text, source_claim_ids, certainty, transformation, evidence_refs?}], dropped:[{source_claim_ids, reason}]}
                               transformation is one of carried, paraphrased, merged, narrowed, generalized (integrity.contracts
                               TRANSFORMATION_MEANINGS says what each records; list_claims.py --json prints them as synthesis_format):
                               a category, never a description of the edit. The merged synthesis is relayed as the JSON the router
                               receives, so the hub's contract validation decides it: a value outside the contract (free text in
                               transformation, say), a malformed claim or a file that is not JSON is a REJECTED receipt (INT-REQ-009,
                               with INT-SYNTH-014 naming each value outside a closed vocabulary), recorded and counted as a failed
                               synthesis, never an exception that stops the round.
                               A claim's optional evidence_refs ([{document_id, locator?, excerpt?}]) are passed on as written. A claim
                               without them keeps the references of its cited material source claims whose excerpts its text
                               reproduces word for word (``evidence_refs_copied`` on the synthesis record), so a synthesis that quotes
                               its sources' evidence is not charged INT-LEDGER-004 for a field the format lacked; one that drops or
                               rewords the evidence still is.
  Peer exchange: a specialist file may carry "group": <id> (tasks of one group share one hub task, plan and ledger) and
  "peer_of": <task_id> (this agent answers only after the peer task's delivered report has been RELAYED to it through the
  hub; the relayed report's original_response is then supplied to it as the document peer:<task_id>, so its quotations of
  the peer are checked like any other, and both reports share the cross-agent consistency pool). The plan gives each agent
  of another subject its own branch (WorkPlan.agent_subjects) and each agent set a different task type its own task type
  (WorkPlan.agent_task_types), so a History peer asked for a short_answer on an analytical_paragraph task carries
  short_answer on its request, report and forward (INT-HANDOFF-010 compares against it). relay_peer.py builds the same plan
  through group_plan() and writes <round>/relayed/<task_id>.json, the only thing the peer-dependent agent may read (the
  delivered payload; the router's receipt of the relay goes to relayed/<task_id>.router.json, never to a specialist).
  A re-run never delivers that recorded payload in place of the peer task's reply: the genuine pass parses the raw
  response_text with the code as it stands, like every other task, so a fix to a parser shows on the re-run's receipts.
  The recording is used only for the document the peer-dependent agent read (peer:<task_id> is its original_response),
  and each genuine record of a peer task carries ``recorded_relay_checks``: whether the recorded payload equals the
  current parse (created_at aside) and, when it does not, the payload fields and the claims that differ, with both
  values. results.json (``recorded_relay_checks``) and summary.md list every check, so a receipt that differs from the
  recorded relay is never read as the receipt the agent was shown.
  <round>/adjudications/translation_fidelity.json  optional: an adjudicator's judgments of translation fidelity, one per translation
                               ({file or task_id, claim_id, verdict faithful|unfaithful, translation_sha256?, claim_text_sha256?};
                               load_adjudications). A judgment counts only for a translation this run served whose digests match.
Outputs: <round>/results.json and <round>/summary.md. ``python run_arena.py <round> [--fail-on-qualification]``: with the flag
the exit status is 1 when the run is qualified (below), so a translation-regression run that lost expected translations fails.

Measures. The harness reports separate measures, each with its own numerator and denominator, and never combines two into
one rate (results.json ``metrics``; summary.md 'Measures', under the headline):
  - transport: the functional count defined below (genuine traffic delivered and decided; injected faults named). It does
    not judge whether a finding is true, whether a translation is faithful or whether an answer is better;
  - fixture coverage: of the recorded translations (translations/*.json), how many this run served (the pipeline
    translated their claims with them) and how many it lost, by reason (``LOST_REASONS``: report not delivered, claim id
    no longer delivered, refused as stale, claim not eligible, dropped by the channel, verification failed); a served
    translation without a recorded claim-text digest is counted as bound by claim id only;
  - translation fidelity: faithful translations of those an adjudicator judged and that apply to this run (``adjudicate``);
    without an adjudication file it is 'not adjudicated' and no figure is given. The engine never decides fidelity;
  - claim counts of the genuine pass: extracted, eligible, attempted, completed (a definitive verdict displayed), faithful
    (where adjudicated) and approved (displayed ENTAILED with no error-level finding on the claim: what the receipt presents
    as verified, not a release decision), each a count of its own (``claim_measures``); beside them, the approved claims
    whose proof rests on an unresolved dependency (an ungrounded premise, or one whose task or source authority no check
    validated) and the claims whose release assessment permits releasing the answer (``ClaimVerificationOutcome.release``,
    the application's rule, kept apart from the formal status; a replay calls no fidelity reviewer, so it permits none);
  - latency of the hub per transmission in this run (a description of the run, not a stress measurement), and cost (no
    provider is called).
A run is qualified, in the summary's title and in results.json (``qualified``, ``qualifications``), when it lost recorded
translations (TRANSLATIONS_LOST), served translations bound by claim id only (FIXTURES_UNBOUND), or holds adjudications
that do not apply to it (ADJUDICATIONS_NOT_APPLIED): its translation figures then describe a different set of translations
from the recorded round's.

Fault mutations applied to every specialist text: invented_quotation (double marks), invented_quotation_single (the same
invented words in single marks), altered_quotation (a real quotation changed by one word; skipped when the text has none),
self_certification, wrong_arithmetic, chronology_error. The altered quotation is the first quotation found verbatim in a
supplied text (a relayed peer report included), else the first quotation; one alphabetic word of it is changed (the middle
word when it is a word, never a figure or a mark, 'ly' before any punctuation: 'boxly.'), inside the quoted span itself,
never at an earlier occurrence of the same words in the prose. With a supplied text of the task's own an invented or
altered quotation is expected as INT-REQ-003 only (the hub must refute it, not call it unverifiable). When the task's only
supplied text is a relayed peer report, an invented quotation is expected as INT-REQ-003 or CORE-SRC-003 (credited to 'the
narrator' when no narrated text was supplied, it is unverifiable rather than refuted) and an altered one as INT-REQ-003.
Without any supplied text a quotation is unverifiable rather than refuted and is expected as CORE-SRC-003.

STEM mutations (stem_mutations.py), applied in addition and only to answers of STEM subjects (the subjects routed to the
sciences, mathematics or computer_science branch): stem_arithmetic_slip (one stated result of a worked chain changed;
INT-SUBJ-001), stem_wrong_unit (a stated result's unit replaced by one of another dimension; ST-DIM-001 or ST-DIM-002),
stem_substitution (a value the request gives, substituted into a calculation, written as another value; INT-SUBJ-001).
Each is skipped when the answer has no site for it. The injection is named when a finding of its code names a claim
that carries the mutated text. An injection no finding names is a miss, whatever the reason, and is never excused: when
the receipt itself names the injected claim of a STEM mutation undecided (an ST-UNDEC finding: a relation outside the
encodings, a symbol with no stated value), the failure reason quotes that finding, so a miss that comes from a limit of
the encodings is shown as one, and it stays a failure of the transport measure. Every other subject's round is unchanged.

Functional-rate definition (deterministic; this is the transport measure): a transmission counts as functional when the
hub produced a receipt without raising, the receipt status is consistent with the input
(a genuine response is not REJECTED; a response carrying an injected fault shows the
expected finding), and any translator output was either validated and decided by the
engine or rejected with diagnostics (never INTERNAL_ERROR; a fixture refused as stale is
neither). The expected finding must name the injection: a finding of the expected code (for
self_certification, one of SELF_REPORT_CODES) that names an injected claim (a delivered claim
whose text or quotation excerpt carries the injected words, INJECTION_MARKERS; for
altered_quotation the altered quotation) or quotes the injected words in its message, and that
the genuine record of the same task does not already carry. A code that is present only for what
the specialist's own text explains (hi-p3's CORE-SRC-003 for its own 'smokeless air') does not
count. A failing record says why under ``failure_reasons``.

The combinator's synthesis of a task (or of a peer group: one synthesis citing every delivered report) is a
transmission of its own: a record of variant ``synthesis``, counted in the rate and in ``by_variant``. In a round that
carries syntheses every group has exactly one synthesis record, made after the group's last member whatever happened to
the members (a crash, a rejection, a peer report never relayed): the synthesis of the members that were delivered is
relayed and its receipt kept, so the number of transmissions does not depend on what failed. It is functional when the
hub produced a receipt without raising, the synthesis was delivered (a genuine synthesis of the delivered reports is not
REJECTED, by the same conservative rule as a genuine response), no check on it failed internally (INT-SYNTH-013, or a
joint check left undecided with INTERNAL_ERROR) and every member of the group was delivered (a member that was not is
named under ``members_not_delivered``: the router received only part of the group's reports). A group with no delivered
member, or a round that carries syntheses but none for a delivered group, records that group's synthesis as a failure.
The record keeps every finding with its claim ids and its full message (``finding_dict``), as do the genuine and
peer-relay records (mutation records cut messages to 300 characters).

Each mutation record also keeps ``injected_claim_ids``, ``named_by`` (the findings that named the
injection), ``unexplained_findings`` (findings the genuine record does not carry and that do not
name the injection; a changed genuine finding keeps its old message as ``baseline_message``) and
``baseline_findings_absent`` (errors and warnings of the genuine record the variant lost). These do
not change the functional rate: they are either consequences of the injected words (a word bound
crossed, one more quotation in a paragraph) or wrong receipts, and results.json
(``mutations_with_unexplained_findings``) and summary.md list them with their messages so a reader
can tell which. ``genuine_with_errors`` lists every genuine transmission, peer relay and combinator
synthesis whose receipt carries an error or a warning, with each finding's code, severity, claim ids
and full message (``codes`` keeps the error codes, ``warning_codes`` the warning codes; a synthesis
entry also names its ``synthesis_id``).

Per claim outcome the record keeps the display status, the translation status, the interpretation's ambiguity flags
(why a claim is AMBIGUOUS_TRANSLATION), the translation diagnostics, and for a verified problem the engine status with
the number of premises relied on, how many of those are ungrounded (assumptions, specialist inferences, unverified
quotations) and how many are unverified, so an ENTAILED verdict is read together with what it rests on. It also keeps
what any other verdict rests on: the number of premises of the translated problem with how many are ungrounded and
unverified (the engine's own rule), the conclusion's label, the engine's diagnostic codes and the assignment the engine
returned (``model``: the counterexample of a COUNTEREXAMPLE, the witness of a CONSISTENT or SATISFIABLE result). A
COUNTEREXAMPLE has no core: it holds every premise of the problem and falsifies the conclusion.
Translation outcomes are provider-dependent: ``provider_dependent_translation_outcomes`` counts the genuine pass only
(every eligible claim with a fixture exactly once; the distinct-claim counts are reported beside it) and
``translation_outcomes_by_variant`` keeps the totals of every variant, which repeat the same claims.

The rate does not judge whether a finding is true. A genuine transmission, peer relay or combinator synthesis whose
receipt carries an error-level finding is still functional when the hub delivered it and decided every check, whether
the finding names a real fault of the specialist or is a false one. ``genuine_receipts_with_errors`` (results.json) and
the line under the headline of summary.md say how many such records carry an error-level finding, how many carry
warnings only, and that they are counted functional. ``displayed_non_entailed_definitive_outcomes`` lists every genuine
claim shown to the router with a definitive verdict other than ENTAILED (COUNTEREXAMPLE: the claim does not follow;
INCONSISTENT_PREMISES; a consistency or satisfiability verdict), with its claim id and what the verdict rests on, and
summary.md lists each one under the translation outcomes, as it names the ENTAILED verdicts that rest only on
ungrounded premises (``entailed_dependencies.resting_only_on_ungrounded_premises_claims``). Beside them it counts, by
rule, the genuine claims whose encoding got no verdict (displayed INVALID_FORMALIZATION), with each claim id
(``withheld_verdicts``): a definitive engine status withheld (E108 vacuous result, E110 unasserted figure, E111 unencoded
reason, E112 circular encoding; E110 and E111 only with source-linked evidence) or an encoding the translation pipeline
rejected before the engine ran (E112 circular, 'stated precision': a rounded figure at another precision than the source
states, 'exactness': an exact or given figure widened). The genuine verdicts that stand with an advisory coverage
warning (W110, W111: the encoding leaves open a figure no source asserts) are counted apart
(``advisory_coverage_warnings``). A translation fixture recorded under a claim id the current parse does not deliver is never served; each
genuine record names such fixtures (``fixtures_matching_no_delivered_claim``) and results.json and summary.md total them
(``translation_fixtures_matching_no_delivered_claim``), so a smaller outcome count is not read as fewer eligible claims.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
import time
import traceback
import unicodedata
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stem_mutations import STEM_MUTATIONS, is_stem_subject, mutate_stem  # noqa: E402

from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.generic_parser import agent_claim_tag
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.runner import ungrounded_dependencies, unverified_dependencies
from epinoic_logic.engine.statuses import DEFINITIVE, VerificationStatus
from epinoic_logic.integrity import AgentRole, WorkPlan
from epinoic_logic.integrity.contracts import ConflictRecord, LedgerEntry, Synthesis, SynthesizedClaim
from epinoic_logic.translate.contracts import ClaimRecord, ClaimVerificationOutcome, SpecialistReport, SuppliedText, TranslationStatus, sha256_text
from epinoic_logic.translate.eligibility import decide_eligibility
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator, apply_subject_policy
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider
from epinoic_logic.translate.subjects import resolve_profile

KEY = b"arena-signing-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
#: Codes under which the infrastructure names an agent's self-certification (core pack, hand-off check, subject pack).
SELF_REPORT_CODES = ("CORE-SELF-001", "INT-HANDOFF-006", "ES-META-001")
#: Mutations in the order they are applied; the variant index is part of the report id.
MUTATIONS = ("invented_quotation", "invented_quotation_single", "altered_quotation", "self_certification", "wrong_arithmetic", "chronology_error")
#: Mutations that invent or alter a quotation: INT-REQ-003 against a supplied text, CORE-SRC-003 (unverifiable) without one.
QUOTATION_MUTATIONS = ("invented_quotation", "invented_quotation_single", "altered_quotation")
#: The fixture provider's own refusal of a fixture produced for another claim text.
STALE_FIXTURE_MARK = "stale fixture"
STALE_BUCKET = "STALE_FIXTURE_REFUSED"
#: Definitive verdicts other than ENTAILED. Displayed on a claim, each tells the router something about the encoding of
#: that claim (COUNTEREXAMPLE: it does not follow from its premises; INCONSISTENT_PREMISES: its premises conflict), so
#: summary.md names every one with its claim id and what it rests on.
DEFINITIVE_NON_ENTAILED = frozenset(s.value for s in DEFINITIVE) - {VerificationStatus.ENTAILED.value}
#: How many assignments of a counterexample or witness a record keeps.
MODEL_KEPT = 16


#: What each appending mutation adds to the specialist's text (altered_quotation changes a real quotation instead).
INJECTED_TEXT = {
    "invented_quotation": ' The narrator also insists that "the river carried every secret of the town", which seals the point.',
    # the same invented words in single quotation marks: both parsers delimit a single-quoted span of two or more words
    "invented_quotation_single": " The narrator also insists that 'the river carried every secret of the town', which seals the point.",
    "self_certification": "\n\nVERIFIED: all claims checked and confirmed.",
    "wrong_arithmetic": " Enrolment rose from 200 to 260 students, an increase of 45 per cent.",
    "chronology_error": " The reform came in March 1931, after the election of October 1932 had changed the balance.",
}
#: Distinctive words of each injection. A finding names the injection when its message carries one of them or when it
#: names an injected claim: a delivered claim whose text or quotation excerpt carries one. The words occur in no
#: genuine text, so a finding the genuine text already explains can never stand in for the injected fault.
INJECTION_MARKERS = {
    "invented_quotation": ("the river carried every secret of the town",),
    "invented_quotation_single": ("the river carried every secret of the town",),
    "self_certification": ("VERIFIED: all claims checked and confirmed",),
    "wrong_arithmetic": ("Enrolment rose from 200 to 260 students", "an increase of 45 per cent"),
    "chronology_error": ("The reform came in March 1931", "after the election of October 1932"),
}
_QUOTE_FOLD = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "«": '"', "»": '"'})
_HEX_ID_RE = re.compile(r"\b(?=[0-9a-f]*[a-f])[0-9a-f]{8,}\b")


_WORD_CORE_RE = re.compile(r"^(\W*)(.*?)(\W*)$", re.DOTALL)


def alter_word(quotation: str) -> str | None:
    """``quotation`` with one alphabetic word changed: its middle word when that word's letters (leading and trailing
    punctuation aside) are all alphabetic, else the nearest such word of three letters or more (then of any length);
    'ly' is appended to its letters, or taken off a word that ends in it (never after punctuation: 'box.' becomes
    'boxly.', not 'box.ly'; a figure or a mark is never the word changed). None when the quotation has no alphabetic
    word. The quotation's spacing and line breaks are kept."""
    words = list(re.finditer(r"\S+", quotation))
    mid = len(words) // 2
    order = sorted(range(len(words)), key=lambda i: (abs(i - mid), i < mid))  # the middle, then outward, the later first

    def core(i: int) -> tuple[str, str, str]:
        m = _WORD_CORE_RE.match(words[i].group(0))
        return m.group(1), m.group(2), m.group(3)
    for min_letters in (0, 3, 1):
        # 0: the middle word itself, as the mutation always chose, when it is a word; then the nearest word
        pick = next((i for i in (order[:1] if min_letters == 0 else order) if core(i)[1].isalpha() and len(core(i)[1]) >= min_letters), None)
        if pick is not None:
            lead, letters, trail = core(pick)
            letters = letters[:-2] if letters.endswith("ly") and len(letters) >= 4 else letters + "ly"
            w = words[pick]
            return quotation[:w.start()] + lead + letters + trail + quotation[w.end():]
    return None


def quotation_to_alter(text: str, texts=()) -> tuple[int, int, str, str] | None:
    """The quotation the altered_quotation mutation changes, as ``(start, end, inner, altered)``: ``start``/``end`` are the
    offsets of the quoted span (marks included) as the parsers delimit it (any mark style; never the prose between two
    quotations), ``inner`` the writer's words between the marks and ``altered`` the same words with one alphabetic word
    changed (``alter_word``). With supplied texts (``texts``: SuppliedText, a relayed peer report included) it is the first
    quotation found verbatim in one of them, so the mutation misquotes a text the agent was given rather than the request
    or its own phrasing; a text that quotes none of its supplied texts (or has none) has its first quotation altered.
    None when the text has no quotation to alter."""
    from epinoic_logic.adapters.markdown import find_quotation_spans
    from epinoic_logic.adapters.sources import check_excerpt
    spans = [(a, b, inner) for a, b, inner in find_quotation_spans(text) if len(inner) >= 12 and inner[:1].isalpha()]
    spans = [(a, b, inner, alt) for a, b, inner in spans if (alt := alter_word(inner)) is not None]
    if not spans:
        return None
    docs = {t.document_id: t for t in texts}
    located = [s for s in spans if any(check_excerpt(s[2], d, docs).status == "found" for d in docs)]
    return (located or spans)[0]


def altered_quotation(text: str, texts=()) -> tuple[str, str] | None:
    """``(quotation, altered quotation)`` of ``quotation_to_alter`` (the words between the marks), or None."""
    q = quotation_to_alter(text, texts)
    return (q[2], q[3]) if q is not None else None


def mutate(text: str, kind: str, texts=()) -> tuple[str, str]:
    """Return (mutated_text, expected_code). Mutations are applied to the specialist's own text; ``texts`` are the
    supplied texts of the task (the altered quotation is one of theirs when the text quotes them)."""
    if kind in ("invented_quotation", "invented_quotation_single"):
        return text + INJECTED_TEXT[kind], "INT-REQ-003|CORE-SRC-003"
    if kind == "altered_quotation":
        q = quotation_to_alter(text, texts)
        if q is None:
            return text, "SKIP"
        a, b, inner, altered = q
        # changed inside the quoted span itself: the same words elsewhere in the prose (mai-t13's 'complete years'
        # before its quotation) are left as they are
        return text[:a] + text[a:b].replace(inner, altered, 1) + text[b:], "INT-REQ-003"
    if kind == "self_certification":
        return text + INJECTED_TEXT[kind], "NONE"
    if kind in ("wrong_arithmetic", "chronology_error"):
        return text + INJECTED_TEXT[kind], "INT-SUBJ-001"
    raise ValueError(kind)


def quotation_expectation(kind: str, expected: str, *, own_texts: bool, any_text: bool) -> str:
    """The code a quotation mutation must be named by, from what the task supplies. A task with a supplied text of its own
    refutes an invented or altered quotation: INT-REQ-003 ('not found in the supplied texts'), never only the
    unverifiable CORE-SRC-003. A task whose only supplied text is a relayed peer report keeps ``mutate``'s expectation
    (an invented quotation credited to 'the narrator' when no narrated text was supplied is unverifiable, not refuted, so
    either code; an altered quotation of the report INT-REQ-003). Without any supplied text a quotation is unverifiable
    rather than refuted: CORE-SRC-003. Other mutations and a skipped one are returned unchanged."""
    if kind not in QUOTATION_MUTATIONS or expected == "SKIP":
        return expected
    if own_texts:
        return "INT-REQ-003"
    return expected if any_text else "CORE-SRC-003"


class Injection(NamedTuple):
    """What identifies an injected fault on a receipt: its words (``markers``) and, for an appended paragraph, regular
    expressions for the place a finding may name it by instead (``locations``: 'paragraph 5, sentence 1')."""
    markers: tuple[str, ...]
    locations: tuple[str, ...] = ()
    words_added: int = 0


def paragraph_count(text: str) -> int:
    """Blank-line blocks with content, as the receipts number paragraphs."""
    return len([b for b in re.split(r"\n[ \t\r]*\n", text.replace("\r\n", "\n")) if b.strip()])


def stem_variant(text: str, question: str, kind: str) -> tuple[str, str]:
    """``(mutated_text, expected codes joined by '|')`` of a STEM mutation, or ``(text, 'SKIP')`` when the answer has no site."""
    inj = mutate_stem(text, question, kind)
    return (text, "SKIP") if inj is None else (inj.text, "|".join(inj.expected))


def undecided_on(rc, claim_ids) -> list[str]:
    """The receipt's own findings that name one of ``claim_ids`` undecided (ST-UNDEC-*: a relation outside the encodings,
    a symbol with no stated value), each as ``code ('message')``. Quoted in the failure reason of an injection no finding
    named, so a miss that comes from a limit of the encodings reads as one; it never changes whether the record counts."""
    wanted = set(claim_ids)
    return sorted({f"{sf.code} ('{sf.message[:160]}')" for sf in rc.structural_findings if sf.code.startswith("ST-UNDEC") and set(sf.claim_ids) & wanted})


def injection(text: str, kind: str, texts=(), question: str = "") -> Injection:
    """How ``mutate(text, kind, texts)``'s injection is recognised on a receipt. For altered_quotation the marker is the
    altered quotation; for self_certification (appended as a paragraph of its own) a finding may also name its place; for a
    STEM mutation (``question``: the request it answers) the marker is the mutated stretch of the answer."""
    if kind in STEM_MUTATIONS:
        inj = mutate_stem(text, question, kind)
        return Injection((inj.marker,) if inj is not None else (), (), 0)
    mutated = mutate(text, kind, texts)[0]
    added = len(mutated.split()) - len(text.split())
    if kind == "altered_quotation":
        alt = altered_quotation(text, texts)
        return Injection((alt[1],) if alt is not None else (), (), added)
    locations = (rf"\bparagraph {paragraph_count(mutated)}, sentence 1\b",) if kind == "self_certification" else ()
    return Injection(INJECTION_MARKERS.get(kind, ()), locations, added)


def norm_text(s: str) -> str:
    """Case-folded, quote-folded, whitespace-collapsed text for marker matching."""
    return " ".join(unicodedata.normalize("NFKC", s).translate(_QUOTE_FOLD).casefold().split())


def finding_dict(f) -> dict:
    """A receipt finding (IntegrityFinding or StructuralFinding) as the harness compares it: full message, never cut."""
    return {"code": f.code, "severity": f.severity, "claim_ids": list(f.claim_ids), "message": f.message}


def brief(f: dict, n: int = 300) -> dict:
    """A finding as a record keeps it (message and any genuine-record message cut to ``n`` characters)."""
    return {k: (v[:n] if k in ("message", "baseline_message") and isinstance(v, str) else v) for k, v in f.items()}


def finding_key(f: dict, task_id: str) -> tuple:
    """Identity of a finding across the genuine record and a variant of the same task: code, severity, claim ids and
    message, with the per-variant report id and generated hex ids (message, receipt, problem ids) folded."""
    msg = re.sub(rf"rep-{re.escape(task_id)}-\d+", f"rep-{task_id}-*", f["message"])
    return f["code"], f["severity"], tuple(sorted(f["claim_ids"])), norm_text(_HEX_ID_RE.sub("<id>", msg))


def injected_claim_ids(claims: list[dict], markers: tuple[str, ...]) -> list[str]:
    """Delivered claims that carry the injection: the claim text or a source excerpt contains one of the markers."""
    ms = [norm_text(m) for m in markers if m]
    out = []
    for c in claims:
        hay = [c.get("claim_text") or ""] + [r.get("excerpt") or "" for r in c.get("source_refs", [])]
        if any(m in norm_text(h) for h in hay for m in ms):
            out.append(c["claim_id"])
    return out


def names_injection(f: dict, inj: Injection, injected_ids) -> bool:
    """True when the finding names an injected claim, quotes the injected words or names the injected paragraph."""
    if set(f["claim_ids"]) & set(injected_ids):
        return True
    msg = norm_text(f["message"])
    return any(norm_text(m) in msg for m in inj.markers if m) or any(re.search(p, f["message"]) for p in inj.locations)


def findings_naming_injection(findings: list[dict], codes, inj: Injection, injected_ids, baseline: list[dict], task_id: str) -> list[dict]:
    """Findings of one of ``codes`` that name the injection and are not already on the genuine record (a finding the
    genuine text explains, such as a CORE-SRC-003 for a quotation the specialist itself wrote, never counts)."""
    base = {finding_key(b, task_id) for b in baseline}
    return [f for f in findings if f["code"] in codes and finding_key(f, task_id) not in base and names_injection(f, inj, injected_ids)]


def diff_against_baseline(findings: list[dict], baseline: list[dict], inj: Injection, injected_ids, task_id: str,
                          baseline_constraints: dict[str, str] | None = None) -> tuple[list[dict], list[dict]]:
    """(unexplained, absent). ``unexplained``: findings of a variant that the genuine record does not carry and that do
    not name the injection; when a genuine finding of the same code on the same claims changed, its message is kept as
    ``baseline_message``. ``absent``: error or warning findings of the genuine record that the variant lost without a
    changed counterpart. Either is a consequence of the injected words (a word bound crossed, a quotation count
    changed) or a wrong receipt; the record lists them so a reader can tell which. An unexplained INT-REQ-005 carries
    the genuine record's measurement of the same constraint (``genuine_constraint``, from ``baseline_constraints``) and
    the number of words the mutation added (``words_added``), so a crossed word bound can be checked by subtraction."""
    vkeys = {finding_key(f, task_id) for f in findings}
    bkeys = {finding_key(b, task_id) for b in baseline}
    gone = [b for b in baseline if finding_key(b, task_id) not in vkeys]
    paired: set[int] = set()
    unexplained = []
    for f in findings:
        if finding_key(f, task_id) in bkeys:
            continue
        match = next((i for i, b in enumerate(gone) if i not in paired and b["code"] == f["code"] and b["severity"] == f["severity"] and set(b["claim_ids"]) <= set(f["claim_ids"])), None)
        if match is not None:
            paired.add(match)
        if names_injection(f, inj, injected_ids):
            continue
        entry = dict(f)
        if match is not None:
            entry["baseline_message"] = gone[match]["message"]
        cm = re.match(r"constraint (\S+) not satisfied", f["message"]) if f["code"] == "INT-REQ-005" else None
        if cm:
            entry["genuine_constraint"] = (baseline_constraints or {}).get(cm.group(1))
            entry["words_added"] = inj.words_added
        unexplained.append(entry)
    absent = [b for i, b in enumerate(gone) if i not in paired and b["severity"] in ("error", "warning")]
    return unexplained, absent


def supplied(item: dict) -> list[SuppliedText]:
    return [SuppliedText(document_id=t["document_id"], title=t.get("title"), author=t.get("author"), text=t["text"], locator_scheme=t.get("locator_scheme", "none")) for t in item.get("supplied_texts", [])]


def load_items(spec_dir: Path, include_pending: bool = False) -> list[dict]:
    """Specialist files in name order, peer-dependent tasks after the tasks they depend on.
    With ``include_pending``, tasks of <round>/tasks.json that have no specialist file yet are
    added (marked ``_pending``) so a group's plan can name every agent before all have answered."""
    items = []
    for sp in sorted(spec_dir.glob("*.json")):
        item = json.loads(sp.read_text())
        item["_path"] = sp
        items.append(item)
    tasks_file = spec_dir.parent / "tasks.json"
    if include_pending and tasks_file.exists():
        have = {it["task_id"] for it in items}
        for task in json.loads(tasks_file.read_text()):
            if task["task_id"] not in have:
                items.append({**task, "_path": spec_dir / f"{task['task_id']}.json", "_pending": True})
    order = {it["task_id"]: i for i, it in enumerate(items)}
    items.sort(key=lambda it: (1 if it.get("peer_of") else 0, order[it["task_id"]]))
    return items


def group_of(item: dict) -> str:
    """The hub task an input belongs to: its declared group, else its own file (variants of one task that share a
    task_id are separate hub tasks, each with its own channel and report ids)."""
    return item.get("group") or item["_path"].stem


def group_plan(items: list[dict], group: str) -> WorkPlan:
    """One plan per group: the last task of the group is the deliverable (its subject and task type are the plan's);
    every other agent of a different subject is listed in agent_subjects and every agent set a different task type in
    agent_task_types (the History peer of an English deliverable answers a short_answer, not an analytical_paragraph);
    peer documents are in scope. relay_peer() and run_round() both build their plans here, so they agree."""
    gitems = [it for it in items if group_of(it) == group] or [next(it for it in items if it["task_id"] == group)]
    primary = gitems[-1]
    primary_task_type = primary.get("task_type", "analytical_paragraph")
    agents: list[str] = []
    for it in gitems:
        if it["agent_id"] not in agents:
            agents.append(it["agent_id"])
    agent_subjects = {it["agent_id"]: it["subject"] for it in gitems if it["subject"] != primary["subject"]}
    agent_task_types = {it["agent_id"]: it["task_type"] for it in gitems if it.get("task_type") and it["task_type"] != primary_task_type}
    doc_ids = sorted({t["document_id"] for it in gitems for t in it.get("supplied_texts", [])} | {f"peer:{it['peer_of']}" for it in gitems if it.get("peer_of")})
    return WorkPlan(plan_id=f"plan-{group}", request_id=f"req-{group}", task_id=group, subject=primary["subject"], task_type=primary_task_type,
                    selected_agent_ids=[*agents, "dummy-combinator"], allowed_document_ids=doc_ids, agent_subjects=agent_subjects, agent_task_types=agent_task_types)


def relay_from_peer(ch, items: list[dict], item: dict, delivered: dict, file_name: str, document_text: str | None = None):
    """Relay the peer task's delivered report to this agent through the channel. Returns
    (record, SuppliedText of the relayed report or None, relayed AgentMessage or None).

    The relay always forwards the report delivered on this channel (the current parse). ``document_text`` is the text the
    peer-dependent agent actually read when relay_peer.py recorded the relay (the recorded payload's original_response);
    when given it is the peer:<task> document, and the record says whether it equals the forwarded original_response."""
    peer = item.get("peer_of")
    if not peer:
        return None, None, None
    peer_item = next((it for it in items if it["task_id"] == peer), None)
    rec = {"file": file_name, "task_id": item["task_id"], "subject": item["subject"], "variant": "peer_relay", "expected": "NONE", "peer_of": peer}
    pm = delivered.get(peer_item["_path"].stem) if peer_item is not None else None
    if peer_item is None or pm is None:
        rec.update(functional=False, error=f"peer report {peer} was not delivered through the hub; nothing to relay")
        return rec, None, None
    peer_report = SpecialistReport.model_validate(pm.payload)
    # The router holds the delivered report and hands it to the peer: a router-to-specialist hand-off on the same ledger,
    # in reply to the delivery it received (so the envelope check ties the forward to that delivery).
    try:
        relayed, rr = ch.relay("router", AgentRole.ROUTER, item["agent_id"], AgentRole.SPECIALIST, peer_report, in_reply_to=pm.message_id)
    except Exception as exc:  # a crash is a translator bug: recorded, never allowed to end the round
        rec.update(functional=False, error=f"{type(exc).__name__}: {exc}", trace=traceback.format_exc()[-1500:])
        return rec, None, None
    rec.update(functional=relayed is not None and rr.status is not TransmissionStatus.REJECTED, status=rr.status.value, branch=rr.branch,
               codes=sorted({f.code for f in rr.findings} | {sf.code for sf in rr.structural_findings}), summary=rr.summary[:400],
               findings=[finding_dict(f) for f in rr.findings], subject_findings=[finding_dict(sf) for sf in rr.structural_findings],
               document_source="recorded relay payload" if document_text is not None else "forwarded report",
               document_matches_forward=document_text is None or document_text == peer_report.original_response)
    if relayed is None:
        return rec, None, None
    text = SuppliedText(document_id=f"peer:{peer}", title=f"{peer_item['agent_id']} report {peer_report.report_id} relayed through the hub", author=peer_item["agent_id"],
                        text=document_text if document_text is not None else peer_report.original_response)
    return rec, text, relayed


def relay_peer(round_dir: Path, task_id: str) -> dict:
    """Receive the peer task's genuine reply, relay the delivered report to the requesting agent and write two files:

    - ``<round>/relayed/<task_id>.json``, the only thing that agent may read of its peer: the specialist_report/1.0
      payload exactly as delivered (with the task ids and the peer document id it is supplied under), and nothing of
      the router's side;
    - ``<round>/relayed/<task_id>.router.json``, the router's record of the relay: the plan as used, the peer request's
      status, the receipt of the peer's delivery (every finding with its message, subject finding, constraint and formal
      check) and the relay record. It is never part of a specialist's bundle: a finding of the hub is the router's to
      weigh, and handed to a specialist it reads as subject advice that may be false (E2E B3; the channel names an
      answer that passes one on as INT-REQ-017).

    Returns both: ``{**specialist file, "router": router file}``."""
    items = load_items(round_dir / "specialists", include_pending=True)
    item = next(it for it in items if it["task_id"] == task_id)
    peer = item["peer_of"]
    peer_item = next(it for it in items if it["task_id"] == peer)
    group = group_of(item)
    hub = RouterHub(signing_key=KEY, config=CFG)
    plan = group_plan(items, group)
    ch = hub.open_task(plan)
    m, _req, rq = hub.dispatch(group, peer_item["agent_id"], peer_item["question"], supplied(peer_item))
    shown = {"task_id": task_id, "peer_of": peer, "delivered": False}
    router = {"task_id": task_id, "peer_of": peer, "plan": {"task_type": plan.task_type, "agent_task_types": dict(plan.agent_task_types), "agent_subjects": dict(plan.agent_subjects)},
              "request": {"status": rq.status.value, "codes": sorted(f.code for f in rq.findings)}, "delivered": False}
    if m is None:
        router["error"] = "request to the peer was rejected"
    else:
        reply, rc = hub.receive(group, m.message_id, peer_item["response_text"], agent_id=peer_item["agent_id"], report_id=f"rep-{peer}-0")
        # the router's record of what the hub attached to the delivery: every finding with its message, not just the codes
        router["peer_receipt"] = {"status": rc.status.value, "codes": sorted({f.code for f in rc.findings} | {sf.code for sf in rc.structural_findings}), "summary": rc.summary,
                                  "findings": [{"code": f.code, "severity": f.severity, "message": f.message, "claim_ids": list(f.claim_ids)} for f in rc.findings],
                                  "subject_findings": [{"code": sf.code, "severity": sf.severity, "message": sf.message, "claim_ids": list(sf.claim_ids), "rule_source": sf.rule_source} for sf in rc.structural_findings],
                                  "constraints": [{"constraint_id": c.constraint_id, "satisfied": c.satisfied, "detail": c.detail} for c in rc.constraint_results],
                                  "formal_checks": [{"check_id": fc.constraint_id, "status": fc.formal_status, "satisfied": fc.satisfied, "detail": fc.detail} for fc in rc.formal_checks]}
        rec, text, relayed = relay_from_peer(ch, items, item, {peer_item["_path"].stem: reply} if reply is not None else {}, item["_path"].name)
        router["relay"] = {k: v for k, v in rec.items() if k != "file"}
        router["delivered"] = shown["delivered"] = relayed is not None
        if relayed is not None:
            shown["document_id"] = text.document_id
            shown["payload"] = relayed.payload  # the specialist_report/1.0 payload exactly as delivered
    (round_dir / "relayed").mkdir(exist_ok=True)
    (round_dir / "relayed" / f"{task_id}.json").write_text(json.dumps(shown, indent=2, ensure_ascii=False, default=str))
    (round_dir / "relayed" / f"{task_id}.router.json").write_text(json.dumps(router, indent=2, ensure_ascii=False, default=str))
    return {**shown, "router": router}


def _quote_fold(s: str) -> str:
    """NFKC, quote marks folded, whitespace collapsed; case is kept (an excerpt is reproduced only with its own letters)."""
    return " ".join(unicodedata.normalize("NFKC", s).translate(_QUOTE_FOLD).split())


def reproduced_evidence_refs(text: str, cited: list[str], source_claims: dict[str, dict]) -> list[dict]:
    """The source references of the cited MATERIAL source claims (the claims INT-LEDGER-004 requires the references of)
    whose excerpt ``text`` reproduces word for word (quote marks, spacing and trailing sentence punctuation aside), each
    as the source carries it, with the source claim it came from. A reference with no excerpt, or whose excerpt the text
    does not reproduce, is not copied, so a synthesized claim that drops or rewords a material source's evidence is
    still charged INT-LEDGER-004. A supporting source's references are not copied (no rule asks for them)."""
    from epinoic_logic.adapters.sources import strip_trailing_punctuation
    hay = _quote_fold(text)
    out: list[dict] = []
    seen: set[tuple] = set()
    for cid in cited:
        src = source_claims.get(cid) or {}
        if src.get("materiality", "material") != "material":
            continue
        for r in src.get("source_refs") or []:
            ex = _quote_fold(strip_trailing_punctuation(r.get("excerpt") or ""))
            key = (r.get("document_id"), r.get("locator"), r.get("excerpt"))
            if ex and ex in hay and key not in seen:
                seen.add(key)
                out.append({"source_claim_id": cid, "document_id": r.get("document_id"), "locator": r.get("locator"), "excerpt": r.get("excerpt")})
    return out


class UnreadableSynthesis(str):
    """The text of a round's syntheses file that is not JSON: the combinator's output as the router would receive it.
    The hub refuses it (INT-REQ-009: a payload that is neither a report nor a synthesis); the harness never raises on it."""


def load_syntheses(syn_dir: Path) -> dict[str, object]:
    """Every syntheses file of the round by file stem: its JSON value as written (a mapping, or whatever else the
    combinator wrote), or an ``UnreadableSynthesis`` holding the text when it is not JSON, so one malformed file never
    stops the round; the hub decides it when the group's synthesis is relayed (synthesis_record)."""
    out: dict[str, object] = {}
    if not syn_dir.exists():
        return out
    for p in sorted(syn_dir.glob("*.json")):
        raw = p.read_text(encoding="utf-8", errors="replace")
        try:
            out[p.stem] = json.loads(raw)
        except ValueError:
            out[p.stem] = UnreadableSynthesis(raw)
    return out


def _as_list(value) -> list:
    return value if isinstance(value, list) else [] if value is None else [value]


#: The fields of a syntheses file (the dummy combinator's format): the file, each synthesized claim, each dropped entry and
#: each conflict record (the synthesis contract's ``ConflictRecord``: a disagreement between the sources the synthesis
#: discloses, citing the source claim ids; repair round 1, re-run review cf-2).
SYNTHESIS_FILE_FIELDS = frozenset({"report_id", "claims", "dropped", "conflicts"})
SYNTHESIS_CLAIM_FIELDS = frozenset({"text", "source_claim_ids", "certainty", "transformation", "evidence_refs"})
SYNTHESIS_DROPPED_FIELDS = frozenset({"source_claim_ids", "reason"})
SYNTHESIS_CONFLICT_FIELDS = frozenset(ConflictRecord.model_fields)


class SynthesisFormatError(ValueError):
    """A syntheses file carries fields the combinator format does not hold. They are refused, never dropped silently: a
    field the synthesis cannot carry (a self-certifying ``verified``, a conflict record, a materiality) would otherwise
    never reach the hub, and the receipt would read as if the combinator had not said it. ``group_synthesis`` carries
    every such field into the mapping it relays, so the hub refuses the synthesis with a receipt (the contract forbids
    unknown fields: INT-REQ-009), and ``synthesis_record`` names the fields on the record with this error's message."""

    def __init__(self, unknown: dict[str, list[str]]) -> None:
        self.unknown = unknown
        super().__init__("syntheses file field(s) the combinator format does not hold, refused rather than dropped: "
                         + "; ".join(f"{where}: {sorted(set(keys))}" for where, keys in unknown.items()))


def synthesis_format_problems(stem: str, syn: dict) -> dict[str, list[str]]:
    """``{where: [unknown field, ...]}`` for one syntheses file (empty when it holds only the format's fields)."""
    out: dict[str, list[str]] = {}
    if not isinstance(syn, dict):
        return {f"syntheses/{stem}.json": ["(not an object)"]}
    extra = sorted(k for k in syn if k not in SYNTHESIS_FILE_FIELDS)
    if extra:
        out[f"syntheses/{stem}.json"] = extra
    for i, c in enumerate(syn.get("claims", []) or []):
        extra = sorted(k for k in c if k not in SYNTHESIS_CLAIM_FIELDS) if isinstance(c, dict) else ["(not an object)"]
        if extra:
            out[f"syntheses/{stem}.json claims[{i}]"] = extra
    for i, d in enumerate(syn.get("dropped", []) or []):
        extra = sorted(k for k in d if k not in SYNTHESIS_DROPPED_FIELDS) if isinstance(d, dict) else ["(not an object)"]
        if extra:
            out[f"syntheses/{stem}.json dropped[{i}]"] = extra
    for i, c in enumerate(_as_list(syn.get("conflicts"))):
        extra = sorted(k for k in c if k not in SYNTHESIS_CONFLICT_FIELDS) if isinstance(c, dict) else ["(not an object)"]
        if extra:
            out[f"syntheses/{stem}.json conflicts[{i}]"] = extra
    return out


#: The fields the synthesis contract itself holds at each level of a syntheses file (``synthesis_format_problems`` names
#: the level): a field the format does not hold but the contract does would be accepted by the hub if relayed.
_CONTRACT_FIELDS = {"file": frozenset(Synthesis.model_fields), "claims": frozenset(SynthesizedClaim.model_fields), "dropped": frozenset(LedgerEntry.model_fields),
                    "conflicts": frozenset(ConflictRecord.model_fields)}


def contract_held_fields(unknown: dict[str, list[str]]) -> dict[str, list[str]]:
    """The fields of ``unknown`` (``synthesis_format_problems``) that the synthesis contract holds at their level
    (``materiality``, ``formal_conclusion`` or ``conflicts``): relayed as written they would reach the router although the
    format given to the combinator does not define them, so the harness refuses such a synthesis without relaying it."""
    out: dict[str, list[str]] = {}
    for where, keys in unknown.items():
        level = "claims" if " claims[" in where else "dropped" if " dropped[" in where else "conflicts" if " conflicts[" in where else "file"
        held = [k for k in keys if k in _CONTRACT_FIELDS[level]]
        if held:
            out[where] = held
    return out


def group_synthesis(items: list[dict], group: str, syntheses: dict, delivered: dict, plan: WorkPlan, notes: dict | None = None):
    """The dummy combinator's synthesis for a hub task, as the JSON the router receives (a mapping of the synthesis/1.0
    shape): the per-report syntheses of every delivered member of the group, merged, citing each delivered report (a
    peer exchange is one task with two reports). The harness never builds the contract models from what the combinator
    wrote: every field is passed on as written (the transformation, certainty and evidence references included) and
    the hub's own contract validation decides it when the mapping is relayed, so a malformed synthesis (a transformation
    written as free text, a claim that is not an object, a file that is not JSON) is a REJECTED receipt with its codes
    (INT-REQ-009, and INT-SYNTH-014 for a value outside a closed vocabulary), never an exception. A member's syntheses
    file that is not JSON (``UnreadableSynthesis``) is what the router would receive for the group: its text is
    returned as the payload. Synthesized claim ids, the cited ids a delivered report holds and the merged student-facing
    text are the harness's (the format leaves them to it); a missing certainty or transformation keeps the defaults it
    always had ("established", "paraphrased"). A field the syntheses format does not hold (``SYNTHESIS_*_FIELDS``) is
    carried as written, at the file level too, so the hub refuses it and it is never dropped silently; the record names
    it (``synthesis_record``, ``synthesis_format_problems``).

    Evidence references: a synthesized claim of the syntheses format may carry ``evidence_refs`` ([{document_id,
    locator?, excerpt?}]), passed on as written. When it carries none, the claim keeps the references of its cited
    material source claims whose excerpts its text reproduces word for word (``reproduced_evidence_refs``): the
    combinator quoted the evidence, and the format had no field to cite it by. ``notes`` (when given) receives ``evidence_refs_copied``:
    {synthesized claim id: the references copied, each with its source claim}."""
    members = [it for it in items if group_of(it) == group and it["_path"].stem in delivered and it["_path"].stem in syntheses]
    if not members:
        return None
    unreadable = next((syntheses[it["_path"].stem] for it in members if isinstance(syntheses[it["_path"].stem], UnreadableSynthesis)), None)
    if unreadable is not None:
        return str(unreadable)
    s_claims: list = []
    ledger: list = []
    conflicts: list = []
    source_ids: list[str] = []
    extra_fields: dict = {}
    copied: dict[str, list[dict]] = {}
    for it in members:
        tid, syn, reply = it["task_id"], syntheses[it["_path"].stem], delivered[it["_path"].stem]
        by_id = {c["claim_id"]: c for c in reply.payload["claims"]}
        prefix = "" if len(members) == 1 else f"{tid}-"
        if not isinstance(syn, dict):  # a JSON value that is no synthesis object: carried as one malformed claim, so the hub names it
            s_claims.append(syn)
            source_ids.append(reply.payload["report_id"])
            continue
        for i, c in enumerate(_as_list(syn.get("claims"))):
            if not isinstance(c, dict):
                s_claims.append(c)
                continue
            sid = f"{prefix}s{i}"
            given = c.get("source_claim_ids", [])
            cited = ([x for x in given if isinstance(x, str) and x in by_id] or given) if isinstance(given, list) else given
            claim = {k: v for k, v in c.items() if k not in ("source_claim_ids",)}
            claim.update(claim_id=sid, source_claim_ids=cited, certainty=c.get("certainty", "established"), transformation=c.get("transformation", "paraphrased"))
            if "evidence_refs" not in c and isinstance(c.get("text"), str) and isinstance(cited, list):
                found = reproduced_evidence_refs(c["text"], [x for x in cited if isinstance(x, str)], by_id)
                claim["evidence_refs"] = [{k: r[k] for k in ("document_id", "locator", "excerpt")} for r in found]
                if found:
                    copied[sid] = found
            s_claims.append(claim)
        for d in _as_list(syn.get("dropped")):  # the 'dropped' list's entries are ledger entries whose transformation is 'dropped'
            ledger.append({**d, "transformation": "dropped"} if isinstance(d, dict) else d)
        for c in _as_list(syn.get("conflicts")):  # disclosed conflicts, as written; with several members the ids are qualified like the claims'
            conflicts.append({**c, "conflict_id": f"{prefix}{c['conflict_id']}"} if prefix and isinstance(c, dict) and isinstance(c.get("conflict_id"), str) else c)
        # a file-level field the format does not hold ('verified', 'conflicts'): carried as written, so the hub refuses it
        extra_fields.update({k: v for k, v in syn.items() if k not in SYNTHESIS_FILE_FIELDS})
        source_ids.append(reply.payload["report_id"])
    if notes is not None:
        notes["evidence_refs_copied"] = copied
    s_text = " ".join(c["text"] for c in s_claims if isinstance(c, dict) and isinstance(c.get("text"), str)) or "(empty)"
    return {**extra_fields, "synthesis_id": f"syn-{group}", "request_id": plan.request_id, "task_id": plan.task_id, "combinator_agent_id": "dummy-combinator",
            "source_report_ids": source_ids, "claims": s_claims, "ledger": ledger, **({"conflicts": conflicts} if conflicts else {}), "text": s_text,
            "text_sha256": sha256_text(s_text), "created_at": "2026-10-11T15:00:00Z"}


def load_recorded_relays(round_dir: Path, items: list[dict]) -> dict[str, dict]:
    """Peer-dependent task id -> {file, peer_of, payload} for every relay relay_peer.py recorded as delivered: the payload
    is what that agent was shown of its peer when it answered."""
    out: dict[str, dict] = {}
    for it in items:
        if not it.get("peer_of"):
            continue
        rel_path = round_dir / "relayed" / f"{it['task_id']}.json"
        if rel_path.exists():
            rel = json.loads(rel_path.read_text())
            if rel.get("delivered") and rel.get("payload"):
                out[it["task_id"]] = {"file": f"relayed/{rel_path.name}", "peer_of": it["peer_of"], "payload": rel["payload"]}
    return out


#: Payload fields a re-run legitimately changes: the delivery timestamp.
VOLATILE_PAYLOAD_FIELDS = frozenset({"created_at"})


def payload_differences(recorded: dict, current: dict | None) -> dict:
    """How a recorded specialist_report/1.0 payload differs from the report the current code delivered for the same raw
    text (``current`` None: the current code did not deliver it). ``fields``: top-level fields other than the claims that
    differ; ``claims_only_recorded`` / ``claims_only_current``: claim ids on one side only; ``claims_changed``: per claim id
    on both sides, each differing field with its recorded and current value; ``claim_order_changed``: the shared claims
    come in another order. ``created_at`` is ignored. ``identical`` is True only when nothing else differs."""
    if current is None:
        return {"identical": False, "current_delivered": False, "fields": [], "claims_only_recorded": [c.get("claim_id") for c in recorded.get("claims", [])],
                "claims_only_current": [], "claims_changed": {}, "claim_order_changed": False}
    fields = sorted(k for k in (recorded.keys() | current.keys()) - VOLATILE_PAYLOAD_FIELDS - {"claims"} if recorded.get(k) != current.get(k))
    rc = {c.get("claim_id"): c for c in recorded.get("claims", [])}
    cc = {c.get("claim_id"): c for c in current.get("claims", [])}
    changed: dict[str, dict] = {}
    for cid in [c for c in rc if c in cc]:
        diff = sorted(k for k in rc[cid].keys() | cc[cid].keys() if rc[cid].get(k) != cc[cid].get(k))
        if diff:
            changed[cid] = {k: {"recorded": rc[cid].get(k), "current": cc[cid].get(k)} for k in diff}
    only_r = [c for c in rc if c not in cc]
    only_c = [c for c in cc if c not in rc]
    order_changed = [c for c in rc if c in cc] != [c for c in cc if c in rc]
    return {"identical": not (fields or only_r or only_c or changed or order_changed), "current_delivered": True, "fields": fields,
            "claims_only_recorded": only_r, "claims_only_current": only_c, "claims_changed": changed, "claim_order_changed": order_changed}


_INTERNAL_RE = re.compile(r"\(INTERNAL_ERROR\)")


def synthesis_failure_reasons(status: str | None, delivered: bool, findings: list[dict], internal_checks: int = 0,
                              undelivered: list[str] | tuple = ()) -> list[str]:
    """Why a combinator synthesis transmission is not functional (empty when it is): it was not delivered (a synthesis of
    the delivered reports is genuine traffic, so REJECTED is a failure, never re-labelled), a check on it failed
    internally (INT-SYNTH-013; a joint check undecided with INTERNAL_ERROR; ``internal_checks`` formal checks or outcomes
    of the receipt with INTERNAL_ERROR), or a member of its group was not delivered through the hub (``undelivered``:
    their task ids), so the synthesis the router received covers only part of the group's reports."""
    reasons = []
    if status == TransmissionStatus.REJECTED.value or not delivered:
        refused = sorted({f["code"] for f in findings if f.get("severity") == "error"})
        reasons.append(f"synthesis receipt {status}{' (' + ', '.join(refused) + ')' if refused else ''}: the combinator's synthesis of the delivered reports was not delivered"
                       + ("; the synthesis does not validate against the synthesis contract (the combinator's output, refused by the hub with a receipt)"
                          if "INT-REQ-009" in refused or "INT-SYNTH-014" in refused else ""))
    internal = [f["code"] for f in findings if f["code"] == "INT-SYNTH-013" or _INTERNAL_RE.search(f["message"])]
    if internal or internal_checks:
        reasons.append(f"{len(internal) + internal_checks} check(s) on the synthesis failed internally (INTERNAL_ERROR){': ' + str(sorted(set(internal))) if internal else ''}")
    if undelivered:
        reasons.append(f"the report(s) of {list(undelivered)} were not delivered through the hub, so the group's synthesis covers only the delivered reports")
    return reasons


def synthesis_record(ch, items: list[dict], item: dict, group: str, syntheses: dict, delivered: dict) -> dict:
    """The combinator's synthesis relay for ``group`` as a record of its own (variant ``synthesis``): the dummy combinator
    sends the merged synthesis of the group's delivered reports to the router on the group's channel. run_round calls it
    after the group's last member whatever happened to the members, so a crash, a rejection or a peer report never
    relayed still leaves exactly one synthesis record per group. A member that was not delivered is named
    (``members_not_delivered``) and makes the record a failure; with no member delivered there is nothing to relay and the
    record fails saying so. The synthesis of the delivered members is still relayed and its receipt kept. Every finding
    is kept with its claim ids and full message; the references copied into synthesized claims are kept as
    ``evidence_refs_copied`` (group_synthesis). The synthesis is relayed as the JSON the router receives, so the hub's
    contract validation decides it: a malformed synthesis is a REJECTED receipt (INT-REQ-009; INT-SYNTH-014 for a value
    outside a closed vocabulary, such as a transformation written as free text) recorded with its findings, and, being
    genuine traffic that was not delivered, a failure. A field a syntheses file carries that the combinator format does not
    hold is refused, never dropped silently, and named on the record (``unknown_synthesis_fields``, and the
    :class:`SynthesisFormatError` message among the ``failure_reasons``; the record is not functional): a field the
    synthesis contract has no place for either is relayed as written, so the hub refuses the synthesis with a receipt
    (INT-REQ-009, the contract forbids unknown fields); a field the contract holds but the format does not define
    (``contract_held_fields``: materiality, formal_conclusion, conflicts) would be accepted if relayed, so the synthesis
    is refused here, not relayed, and the message is also the record's ``error``. Never raises: a crash is recorded as a
    non-functional record."""
    plan = ch.plan
    members = [it for it in items if group_of(it) == group]
    undelivered = [it["task_id"] for it in members if it["_path"].stem not in delivered]
    rec = {"file": item["_path"].name, "task_id": item["task_id"], "subject": plan.subject, "variant": "synthesis", "expected": "NONE", "task_type": plan.task_type,
           "channel": group, "group": group,
           "synthesis_files": [f"syntheses/{it['_path'].stem}.json" for it in members if it["_path"].stem in syntheses]}
    if undelivered:
        rec["members_not_delivered"] = undelivered
    t0 = time.perf_counter()
    try:
        notes: dict = {}
        synthesis = group_synthesis(items, group, syntheses, delivered, plan, notes)
        if synthesis is None:
            if len(undelivered) == len(members):
                rec.update(functional=False, error=f"no report of the group {group!r} was delivered through the hub ({undelivered}): the combinator has nothing to synthesize"
                           + (f", and the round's syntheses {rec['synthesis_files']} cite reports the router never received" if rec["synthesis_files"] else ""))
            else:
                rec.update(functional=False, error=f"no synthesis for the delivered group {group!r}: the round carries syntheses, but none for a delivered member of this group")
            return rec
        if notes.get("evidence_refs_copied"):
            rec["evidence_refs_copied"] = notes["evidence_refs_copied"]
        unknown: dict[str, list[str]] = {}
        for it in members:
            stem = it["_path"].stem
            if stem in delivered and isinstance(syntheses.get(stem), dict):
                unknown.update(synthesis_format_problems(stem, syntheses[stem]))
        held = contract_held_fields(unknown)
        if held:
            # a field the format does not define but the contract holds (materiality, formal_conclusion, conflicts): relayed,
            # the hub would accept it, so the synthesis is refused here, not relayed, and the fields are named
            exc = SynthesisFormatError(unknown)
            rec.update(functional=False, delivered=False, error=str(exc), unknown_synthesis_fields=exc.unknown, contract_held_fields=held,
                       failure_reasons=[str(exc) + f"; the synthesis contract would accept {held} if relayed, so the synthesis was not relayed"])
            return rec
        relayed, rr = ch.relay("dummy-combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, synthesis)
        findings = [finding_dict(f) for f in rr.findings]
        subject = [finding_dict(sf) for sf in rr.structural_findings]
        internal_checks = sum(1 for fc in rr.formal_checks if fc.formal_status == "INTERNAL_ERROR") + sum(1 for o in rr.outcomes if o.display_status.value == "INTERNAL_ERROR")
        reasons = synthesis_failure_reasons(rr.status.value, relayed is not None, findings + subject, internal_checks, undelivered)
        shape = synthesis if isinstance(synthesis, dict) else {}
        if not isinstance(synthesis, dict):
            rec["synthesis_unreadable"] = "a syntheses file of the group is not JSON: its text was relayed as the payload"
        rec.update(functional=not reasons, synthesis_id=shape.get("synthesis_id", f"syn-{group}"), source_report_ids=list(shape.get("source_report_ids") or []),
                   synthesized_claims=len(shape.get("claims") or []),
                   status=rr.status.value, branch=rr.branch, delivered=relayed is not None,
                   codes=sorted({f["code"] for f in findings} | {sf["code"] for sf in subject}), findings=findings, subject_findings=subject,
                   formal_result_ids=list(rr.formal_result_ids), latency_ms=(time.perf_counter() - t0) * 1000.0, summary=rr.summary[:400])
        if unknown:
            # the combinator's file says more than the format carries: relayed as written, refused by the hub with its receipt
            # (the harness did not fail, so no ``error``), and named here
            reasons.append(str(SynthesisFormatError(unknown)))
            rec.update(functional=False, unknown_synthesis_fields=unknown)
        if reasons:
            rec["failure_reasons"] = reasons
    except Exception as exc:  # a crash is a translator bug
        rec.update(functional=False, error=f"{type(exc).__name__}: {exc}", trace=traceback.format_exc()[-1500:])
        if undelivered:
            rec["failure_reasons"] = synthesis_failure_reasons(None, True, [], 0, undelivered)
    return rec


def stale_fixture(o: ClaimVerificationOutcome) -> bool:
    """True when the fixture provider refused its fixture because the claim text differs from the one the fixture was
    produced for: the translation failed by design of the harness, not of the infrastructure."""
    return o.translation.status is TranslationStatus.TRANSLATION_FAILED and any(STALE_FIXTURE_MARK in d for d in o.translation.diagnostics)


def outcome_record(o: ClaimVerificationOutcome) -> dict:
    """What a record keeps per claim outcome: enough to see why a claim is AMBIGUOUS and what a verdict rests on."""
    t, v = o.translation, o.verification
    flags = t.interpretation.ambiguity_flags if t.interpretation is not None else []
    rec = {"claim_id": o.claim_id, "display_status": o.display_status.value, "translation_status": t.status.value,
           "ambiguity_flags": [{"code": f.code, "message": f.message[:300], "alternatives": [a[:200] for a in f.alternatives]} for f in flags],
           "translation_diagnostics": [d[:300] for d in t.diagnostics][:8], "stale_fixture_refused": stale_fixture(o),
           # the pipeline's own eligibility decision for the claim (the claim counts compare it with the harness's)
           "eligible": t.eligibility.eligible}
    if o.release is not None:
        # the release assessment (permission to release the answer on this claim's checks), kept apart from the formal status
        rec.update(release_permitted=o.release.permitted, release_unresolved=[u[:200] for u in o.release.unresolved][:6])
    if v is not None:
        rec.update(engine_status=v.status.value, premises_relied_on=len(v.premises_relied_on), ungrounded_dependencies=len(v.ungrounded_dependencies),
                   unverified_dependencies=len(v.unverified_dependencies), ungrounded_dependency_ids=list(v.ungrounded_dependencies)[:16],
                   engine_diagnostics=[d.message[:200] for d in v.diagnostics][:3], engine_diagnostic_codes=sorted({d.code for d in v.diagnostics}))
        p = t.problem
        if p is not None:
            # what a verdict without a core (a COUNTEREXAMPLE holds every premise) rests on: the problem's premises,
            # counted by the engine's own grounding rule
            ids = [a.id for a in p.premises]
            rec.update(problem_premises=len(ids), problem_ungrounded_premises=len(ungrounded_dependencies(p, ids)),
                       problem_unverified_premises=len(unverified_dependencies(p, ids)),
                       conclusion_label=(p.conclusion.label or "")[:200] if p.conclusion is not None else None)
        model = v.counterexample.assignments if v.counterexample is not None else (v.witness_model or [])
        if model:
            rec.update(model=[f"{a.symbol}={a.value}" for a in model[:MODEL_KEPT]], model_size=len(model))
    return rec


def outcome_bucket(o: dict) -> str:
    return STALE_BUCKET if o.get("stale_fixture_refused") else o["display_status"]


def _record_findings(r: dict) -> list[dict]:
    return r.get("findings", []) + r.get("subject_findings", [])


#: Record variants whose receipts are genuine traffic: a specialist's own reply, the router's forward to a peer, and the
#: combinator's synthesis of the delivered reports.
GENUINE_VARIANTS = ("genuine", "peer_relay", "synthesis")


def genuine_findings_summary(records: list[dict]) -> list[dict]:
    """Every genuine transmission, peer relay and combinator synthesis whose receipt carries an error or a warning, with
    each such finding's code, severity, claim ids and full message: a correct finding against a specialist's or the
    combinator's fault, or a false one."""
    out = []
    for r in records:
        if r["variant"] not in GENUINE_VARIANTS:
            continue
        shown = [f for f in _record_findings(r) if f["severity"] in ("error", "warning")]
        if shown:
            entry = {"file": r["file"], "variant": r["variant"], "status": r.get("status"),
                     "codes": sorted({f["code"] for f in shown if f["severity"] == "error"}),
                     "warning_codes": sorted({f["code"] for f in shown if f["severity"] == "warning"}), "findings": shown}
            if r.get("synthesis_id"):
                entry["synthesis_id"] = r["synthesis_id"]
            if r.get("recorded_relays_differing"):
                entry["recorded_relays_differing"] = list(r["recorded_relays_differing"])
            out.append(entry)
    return out


def _record_tag(r: dict) -> str:
    return f"{r['file']} [{r['variant']}{' ' + r['synthesis_id'] if r.get('synthesis_id') else ''}]"


def genuine_error_receipts(records: list[dict]) -> dict:
    """How many genuine transmissions, peer relays and combinator syntheses carry an error-level finding (and how many
    carry warnings only), and how many of each the rate still counts as functional. The rate does not judge whether a
    finding is true: a correct finding against a specialist's fault and a false finding on a correct statement both
    leave the record functional. ``records_with_errors`` names each such record with its error codes and claim ids."""
    gen = [r for r in records if r["variant"] in GENUINE_VARIANTS]
    errors = [r for r in gen if any(f["severity"] == "error" for f in _record_findings(r))]
    warnings_only = [r for r in gen if r not in errors and any(f["severity"] == "warning" for f in _record_findings(r))]
    return {"genuine_records": len(gen), "with_error_findings": len(errors),
            "with_error_findings_counted_functional": sum(1 for r in errors if r.get("functional")),
            "with_warning_findings_only": len(warnings_only),
            "with_warning_findings_only_counted_functional": sum(1 for r in warnings_only if r.get("functional")),
            "records_with_errors": [{"record": _record_tag(r), "file": r["file"], "variant": r["variant"], "status": r.get("status"), "functional": bool(r.get("functional")),
                                     "errors": [{"code": f["code"], "claim_ids": f["claim_ids"]} for f in _record_findings(r) if f["severity"] == "error"]} for r in errors],
            "note": "the functional rate does not judge whether a finding is true: a record with an error-level finding, true or false, is counted functional when the hub delivered it and decided every check"}


def error_receipt_line(s: dict) -> str:
    """summary.md's line under the headline: the genuine records carrying errors or warnings, all counted functional."""
    named = "; ".join(f"{e['record']}: " + ", ".join(f"{x['code']} {x['claim_ids']}" for x in e["errors"]) for e in s["records_with_errors"])
    return (f"Genuine transmissions, peer relays and combinator syntheses: {s['genuine_records']}. "
            f"With an error-level finding: {s['with_error_findings']}{' (' + named + ')' if named else ''}, of which {s['with_error_findings_counted_functional']} counted functional. "
            f"With warning-level findings only: {s['with_warning_findings_only']}, of which {s['with_warning_findings_only_counted_functional']} counted functional. "
            "The rate does not judge whether a finding is true: a false error on a correct statement is counted functional like a true one, "
            "so read every finding in the genuine section below.")


#: Rules under which a claim's encoding gets no verdict (displayed INVALID_FORMALIZATION): the encoding, not the claim,
#: decided the result. The E-codes are the engine's (a definitive status withheld; E110 and E111 only with source-linked
#: evidence that a source asserts what the encoding left open) and the translation pipeline's (an encoding rejected
#: before it is verified, ``E112: circular`` among its diagnostics); 'stated precision' is the pipeline's rejection of an
#: encoding that reads a rounded figure at another precision than the source states, and 'exactness' its rejection of an
#: exact or task-given figure widened into an interval (a weakening of the claim).
WITHHELD_VERDICT_CODES = {"E108": "vacuous result (no premise used, or a counterexample over zero premises)",
                          "E110": "unasserted figure (a counterexample that only reassigns a figure a source asserts and no premise asserts)",
                          "E111": "unencoded reason (a counterexample that only reassigns conclusion symbols a source states and no premise mentions)",
                          "E112": "circular encoding (ENTAILED from premises that restate the conclusion: assumed, not derived)",
                          "stated precision": "stated precision (a rounded figure encoded at another precision than the source states)",
                          "exactness": "exactness (an exact or task-given figure widened into an interval: a weakening of the claim)"}
_WITHHELD_DIAG_RE = re.compile(r"\b(E108|E110|E111|E112)\b|\b(stated precision|exactness):")
#: The engine's advisory coverage warnings: a COUNTEREXAMPLE that only reassigns a figure the problem defines but never
#: asserts (W110) or conclusion symbols no premise mentions (W111), with no source-linked evidence that a source asserts
#: them. The verdict on the encoding stands (the question may leave the figure open); the count is a coverage measure.
ADVISORY_COVERAGE_CODES = {"W110": "unasserted figure, advisory (the counterexample stands; no source asserts the defined figure)",
                           "W111": "unconstrained symbol, advisory (the counterexample stands; no source states the free symbols)"}


def withheld_verdicts(records: list[dict]) -> dict:
    """Genuine claims (genuine transmission, peer relay or synthesis records) displayed INVALID_FORMALIZATION under one of
    WITHHELD_VERDICT_CODES, named by the engine's diagnostics or by the translation diagnostics (the pipeline rejects a
    circular or rounded-figure encoding before the engine runs): per rule, how many and which ('<file> <claim id>
    (<engine status, or 'rejected at translation'>)'). summary.md gives them beside the line on ENTAILED verdicts resting on
    ungrounded premises, so a circular or vacuous encoding is counted, not only left out of the verdicts."""
    out = {code: {"meaning": meaning, "count": 0, "claims": []} for code, meaning in WITHHELD_VERDICT_CODES.items()}
    for r in records:
        if r["variant"] not in GENUINE_VARIANTS:
            continue
        for o in r.get("outcomes", []):
            if o["display_status"] != "INVALID_FORMALIZATION" or o.get("stale_fixture_refused"):
                continue
            codes = set(o.get("engine_diagnostic_codes") or []) & set(WITHHELD_VERDICT_CODES)
            for d in o.get("translation_diagnostics") or []:
                codes |= {m.group(1) or m.group(2) for m in _WITHHELD_DIAG_RE.finditer(d)}
            for code in sorted(codes):
                out[code]["count"] += 1
                out[code]["claims"].append(f"{r['file']} {o['claim_id']} ({o.get('engine_status') or 'rejected at translation'})")
    return out


def advisory_coverage(records: list[dict]) -> dict:
    """Genuine claims (genuine transmission, peer relay or synthesis records) shown with a definitive verdict that carries
    an advisory coverage warning (ADVISORY_COVERAGE_CODES): per code, how many and which ('<file> <claim id> (<displayed
    status>)'). These verdicts stand; the count says how many rest on a figure or symbol the encoding leaves open."""
    out = {code: {"meaning": meaning, "count": 0, "claims": []} for code, meaning in ADVISORY_COVERAGE_CODES.items()}
    for r in records:
        if r["variant"] not in GENUINE_VARIANTS:
            continue
        for o in r.get("outcomes", []):
            if o.get("stale_fixture_refused"):
                continue
            for code in sorted(set(o.get("engine_diagnostic_codes") or []) & set(ADVISORY_COVERAGE_CODES)):
                out[code]["count"] += 1
                out[code]["claims"].append(f"{r['file']} {o['claim_id']} ({o['display_status']})")
    return out


def advisory_coverage_line(a: dict) -> str:
    """summary.md's line counting the genuine verdicts that carry an advisory coverage warning, by code."""
    parts = [f"{code} {v['meaning'].split(' (')[0]}: {v['count']}" + (f" ({', '.join(v['claims'])})" if v["claims"] else "") for code, v in a.items()]
    return ("- advisory coverage warnings on genuine claims (the verdict on the encoding stands; the encoding leaves a figure or symbol open that no "
            f"source asserts; a coverage measure, not a verdict): {len({c for v in a.values() for c in v['claims']})}; " + "; ".join(parts))


def withheld_verdict_line(w: dict) -> str:
    """summary.md's line counting the genuine claims whose encoding got no verdict, by rule."""
    parts = [f"{code} {v['meaning'].split(' (')[0]}: {v['count']}" if code.startswith("E") else f"{code}: {v['count']}" for code, v in w.items()]
    parts = [p + (f" ({', '.join(v['claims'])})" if v["claims"] else "") for p, v in zip(parts, w.values())]
    return (f"- encodings given no verdict on genuine claims (displayed INVALID_FORMALIZATION: a definitive engine status withheld, or the "
            f"encoding rejected at translation): {len({c for v in w.values() for c in v['claims']})}; " + "; ".join(parts))


def unserved_fixtures(records: list[dict]) -> dict:
    """Translation fixtures recorded under a claim id the current parse does not deliver (never served: their claims get
    no outcome), per file, from the genuine records."""
    per_file = {r["file"]: r["fixtures_matching_no_delivered_claim"] for r in records if r["variant"] == "genuine" and r.get("fixtures_matching_no_delivered_claim")}
    return {"count": sum(len(v) for v in per_file.values()), "by_file": per_file}


def displayed_non_entailed_definitive(records: list[dict]) -> list[dict]:
    """Every genuine claim (genuine transmission, peer relay or synthesis record) whose displayed status is a definitive
    verdict other than ENTAILED, with its claim id and what the verdict rests on. A refused stale fixture is no verdict."""
    keys = ("translation_status", "engine_status", "problem_premises", "problem_ungrounded_premises", "problem_unverified_premises", "premises_relied_on",
            "ungrounded_dependencies", "unverified_dependencies", "ungrounded_dependency_ids", "model", "model_size", "conclusion_label", "engine_diagnostic_codes",
            "engine_diagnostics")
    out = []
    for r in records:
        if r["variant"] not in GENUINE_VARIANTS:
            continue
        for o in r.get("outcomes", []):
            if o["display_status"] in DEFINITIVE_NON_ENTAILED and not o.get("stale_fixture_refused"):
                out.append({"file": r["file"], "variant": r["variant"], "task_id": r.get("task_id"), "claim_id": o["claim_id"], "display_status": o["display_status"],
                            **{k: o[k] for k in keys if k in o}})
    return out


def rests_on_text(o: dict) -> str:
    """What a displayed verdict rests on, in one line of summary.md."""
    parts = []
    if "problem_premises" in o:
        parts.append(f"the problem's {o['problem_premises']} premise(s), {o['problem_ungrounded_premises']} ungrounded and {o['problem_unverified_premises']} unverified")
    if o["display_status"] == VerificationStatus.COUNTEREXAMPLE.value:
        parts.append("no premise relied on: a counterexample has no core, it holds every premise and falsifies the conclusion")
    else:
        ids = o.get("ungrounded_dependency_ids") or []
        parts.append(f"{o.get('premises_relied_on', 0)} premise(s) relied on, {o.get('ungrounded_dependencies', 0)} ungrounded{' ' + str(ids) if ids else ''} and {o.get('unverified_dependencies', 0)} unverified")
    if o.get("model"):
        more = f" (+{o['model_size'] - len(o['model'])} more)" if o.get("model_size", 0) > len(o["model"]) else ""
        parts.append(f"{'counterexample' if o['display_status'] == VerificationStatus.COUNTEREXAMPLE.value else 'model'}: {', '.join(o['model'])}{more}")
    if o.get("conclusion_label"):
        parts.append(f"conclusion: {o['conclusion_label']!r}")
    parts.append(f"engine diagnostics: {o.get('engine_diagnostic_codes') or 'none'}")
    return "; ".join(parts)


def definitive_outcome_lines(entries: list[dict]) -> list[str]:
    """summary.md lines naming every displayed definitive verdict other than ENTAILED on a genuine claim."""
    lines = ["- definitive verdicts other than ENTAILED displayed on genuine claims (each is shown to the router as the engine's verdict on the claim's encoding: "
             f"COUNTEREXAMPLE, the claim does not follow from its premises; INCONSISTENT_PREMISES, its premises conflict): {len(entries)}"]
    lines += [f"  - {e['file']} {e['claim_id']}: {e['display_status']} (translation {e.get('translation_status')}, engine {e.get('engine_status')}); rests on {rests_on_text(e)}" for e in entries]
    return lines


def _render_value(v) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def recorded_relay_lines(checks: list[dict]) -> list[str]:
    """summary.md lines for the recorded peer relays compared with the current parse."""
    lines = []
    for c in checks:
        head = f"- {c['relayed_file']} ({c['peer_of']} relayed to {c['dependent_task_id']})"
        if c["identical"]:
            lines.append(f"{head}: identical to the current parse (created_at aside)")
            continue
        if not c.get("current_delivered", True):
            lines.append(f"{head}: DIFFERS: the current code did not deliver {c['peer_of']}'s reply; the recorded payload was not delivered in its place")
            continue
        lines.append(f"{head}: DIFFERS from the current parse; the genuine pass delivered the current parse and used the recording only for the document the agent read")
        if c["fields"]:
            lines.append(f"  - payload fields that differ: {c['fields']}")
        if c["claims_only_recorded"]:
            lines.append(f"  - claims only in the recording: {c['claims_only_recorded']}")
        if c["claims_only_current"]:
            lines.append(f"  - claims only in the current parse: {c['claims_only_current']}")
        if c.get("claim_order_changed"):
            lines.append("  - the shared claims come in another order")
        for cid, diff in c["claims_changed"].items():
            lines += [f"  - {cid} {k}: recorded {_render_value(v['recorded'])} -> current {_render_value(v['current'])}" for k, v in diff.items()]
    return lines


def unexplained_summary(records: list[dict]) -> list[dict]:
    """Mutation records carrying findings beyond the genuine record that do not name the injection, or that lost an
    error or warning of the genuine record (info-level additions are counted by code)."""
    out = []
    for r in records:
        un = r.get("unexplained_findings") or []
        shown = [f for f in un if f["severity"] in ("error", "warning")]
        info = sorted(f["code"] for f in un if f["severity"] == "info")
        absent = r.get("baseline_findings_absent") or []
        if shown or absent or info:
            out.append({"file": r["file"], "variant": r["variant"], "status": r.get("status"), "functional": bool(r.get("functional")),
                        "injected_claim_ids": r.get("injected_claim_ids", []), "unexplained": shown, "absent": absent, "unexplained_info": info})
    return out


# --- separate measures: transport, fixture coverage, translation fidelity and claim counts ---------------------------
#
# Each measure has its own numerator and denominator and is reported on its own line; none is combined with another
# into one rate. Transport (the functional count) says the hub delivered and decided every transmission and named every
# injected fault; it never says that a translation is faithful or that an answer is better. Fixture coverage says how
# many recorded translations this run could still use; translation fidelity says how many of the translations used were
# judged faithful by an adjudicator; the claim counts say how far each genuine claim went.

#: Display statuses that are a definitive engine verdict on the claim's encoding: a claim shown with one is 'completed'.
DEFINITIVE_DISPLAY = frozenset(s.value for s in DEFINITIVE)
#: Where a round keeps its adjudications of translation fidelity (format in ``load_adjudications``).
ADJUDICATIONS_FILE = Path("adjudications") / "translation_fidelity.json"
#: The two verdicts an adjudication records, and the spellings accepted for each.
FAITHFUL, UNFAITHFUL = "faithful", "unfaithful"
VERDICT_SPELLINGS = {"faithful": FAITHFUL, "f": FAITHFUL, "unfaithful": UNFAITHFUL, "u": UNFAITHFUL}
#: Why a recorded translation was not used in a run, in the order a fixture is tested for them.
LOST_REASONS = {
    "report_not_delivered": "the task's report was not delivered through the hub (a crash, a rejection, or a peer report never relayed)",
    "matching_no_delivered_claim": "its claim id matches no claim the current parse delivers",
    "refused_stale": "the fixture provider refused it: the claim's text differs from the text it was produced for",
    "not_eligible": "its claim is delivered but not eligible for translation under the current policy (the provider is never asked)",
    "dropped_by_channel": "the channel dropped its outcome as stale (INT-STALE-011)",
    "failed_internally": "the claim's verification raised (INT-REQ-006)",
    "no_outcome": "its claim is delivered and eligible but no outcome came back and no finding says why",
}
#: The same reasons as summary.md counts them.
LOST_LABELS = {
    "report_not_delivered": "report not delivered",
    "matching_no_delivered_claim": "match no delivered claim id",
    "refused_stale": "refused as stale (the claim's text changed)",
    "not_eligible": "claim not eligible under the current policy",
    "dropped_by_channel": "dropped by the channel as stale (INT-STALE-011)",
    "failed_internally": "verification failed internally (INT-REQ-006)",
    "no_outcome": "no outcome and no finding saying why",
}
#: Record variants that are injected faults (the transport measure counts them apart from genuine traffic).
INJECTED_VARIANTS = frozenset(MUTATIONS) | frozenset(STEM_MUTATIONS)


def fixture_sha256(value) -> str:
    """Digest of a recorded translation fixture as the translations file holds it: the text itself, or the canonical JSON
    of an object (sorted keys, no spacing). An adjudication names the translation it judged by this digest."""
    if isinstance(value, str):
        return sha256_text(value)
    return sha256_text(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")))


def translation_eligible(claim: ClaimRecord) -> bool:
    """Whether the translation pipeline translates ``claim``: the deterministic eligibility rule narrowed by the claim's
    subject profile, as ``Translator.translate`` decides before it asks any provider. The claim counts use it for claims
    no fixture was recorded for, and compare it with the pipeline's own decision wherever an outcome carries one."""
    return apply_subject_policy(decide_eligibility(claim), resolve_profile(claim.subject)).eligible


def _claims_named(findings: list[dict], code: str) -> set[str]:
    return {cid for f in findings if f["code"] == code for cid in f["claim_ids"]}


def claim_measures(claims: list[ClaimRecord], outcomes: list[dict], findings: list[dict]) -> dict:
    """A genuine record's claims by how far each went, every stage a list of claim ids of its own:

    - ``extracted``: every claim the current parse delivered;
    - ``eligible``: those the translation pipeline would translate (its own decision where an outcome carries one,
      otherwise ``translation_eligible``; where both exist and disagree the claim is listed under
      ``eligibility_disagreements``);
    - ``attempted``: eligible claims the pipeline ran on (a recorded translation was offered: an outcome other than
      NOT_ELIGIBLE, or an outcome the channel dropped as stale, or a verification that raised);
    - ``completed``: attempted claims shown with a definitive engine verdict on their encoding (ENTAILED,
      COUNTEREXAMPLE, INCONSISTENT_PREMISES, CONSISTENT, SATISFIABLE, UNSATISFIABLE); an ambiguous, rejected, withheld,
      unsupported, undecided, refused or failed translation is not completed;
    - ``approved``: completed claims displayed ENTAILED, the one status that reads as success, with no error-level
      finding naming the claim on the receipt. This is the harness's count of what the receipt presents as verified, not
      an application's release decision; ``approved_resting_on_ungrounded_premises`` names those whose proof relies on
      an assumption, a specialist inference or an unverified quotation, and
      ``approved_resting_on_unresolved_dependencies`` those whose proof relies on any unresolved dependency: an ungrounded
      premise, or one whose task or source authority no check validated (the engine's ``unverified_dependencies``);
    - ``release_permitted``: completed claims whose release assessment (``ClaimVerificationOutcome.release``) permits
      releasing the answer on the claim's checks, with no error-level finding naming the claim on the receipt. It is the
      application's rule, kept apart from the formal status: it needs established premises and a current, faithful
      fidelity review made with the evidence, so a replay of recorded translations (no reviewer is called) permits none.

    'faithful' is not decided here: it comes from adjudications (``adjudicate``)."""
    by_id = {o["claim_id"]: o for o in outcomes}
    dropped, failed = _claims_named(findings, "INT-STALE-011"), _claims_named(findings, "INT-REQ-006")
    eligible: list[str] = []
    disagreements: list[str] = []
    for c in claims:
        harness = translation_eligible(c)
        decided = by_id[c.claim_id].get("eligible") if c.claim_id in by_id else None
        if decided is not None and decided != harness:
            disagreements.append(c.claim_id)
        if harness if decided is None else decided:
            eligible.append(c.claim_id)
    attempted = [cid for cid in eligible
                 if (cid in by_id and by_id[cid]["translation_status"] != TranslationStatus.NOT_ELIGIBLE.value) or cid in dropped or cid in failed]
    completed = [cid for cid in attempted if cid in by_id and not by_id[cid].get("stale_fixture_refused") and by_id[cid]["display_status"] in DEFINITIVE_DISPLAY]
    errors = {cid for f in findings if f["severity"] == "error" for cid in f["claim_ids"]}
    approved = [cid for cid in completed if by_id[cid]["display_status"] == VerificationStatus.ENTAILED.value and cid not in errors]
    return {"extracted": [c.claim_id for c in claims], "eligible": eligible, "attempted": attempted, "completed": completed, "approved": approved,
            "approved_resting_on_ungrounded_premises": [cid for cid in approved if by_id[cid].get("ungrounded_dependencies")],
            "approved_resting_on_unresolved_dependencies": [cid for cid in approved
                                                            if by_id[cid].get("ungrounded_dependencies") or by_id[cid].get("unverified_dependencies")],
            "release_permitted": [cid for cid in completed if by_id[cid].get("release_permitted") is True and cid not in errors],
            "eligible_not_attempted": [cid for cid in eligible if cid not in set(attempted)], "eligibility_disagreements": disagreements}


def fixture_claim_ids(recorded_ids, agent: str) -> dict[str, str]:
    """``{claim id a delivery may carry: the recorded fixture id that serves it}``. Each recorded id serves itself; a
    recorded id with no agent qualifier also serves the same claim as the parsers number it on a task with two or more
    agents (``<id>@<agent>``: since B17 the STEM and generic parsers qualify claim ids by agent there). So a translation
    recorded under the bare id before that change still reaches the claim it was produced for, and stays bound to that
    claim's text by its digest (repair round 2, I5: run1's ess-e1b fixtures matched no delivered claim)."""
    recorded_ids = list(recorded_ids)
    out = {rid: rid for rid in recorded_ids}
    tags = sorted({agent, agent_claim_tag(agent)}) if agent else []
    for rid in recorded_ids:
        if "@" in rid:
            continue
        for tag in tags:
            out.setdefault(f"{rid}@{tag}", rid)
    return out


def fixture_for_claim(recorded, recorded_id: str, claim_id: str):
    """The translation recorded under ``recorded_id`` as served to ``claim_id`` (one of its ids, :func:`fixture_claim_ids`):
    served to its own id, it is unchanged; served to the agent-qualified id of the same claim, its problem names that id,
    as a provider asked for the claim under its new id writes it, so the translator's check that a problem is about the
    claim being translated still holds and still refuses a problem about any other claim. A translation whose problem
    names another claim, or that is not a JSON object, is served unchanged (and refused as before)."""
    if claim_id == recorded_id:
        return recorded
    try:
        obj = json.loads(recorded) if isinstance(recorded, str) else recorded
    except ValueError:
        return recorded
    problem = obj.get("problem") if isinstance(obj, dict) else None
    if not isinstance(problem, dict) or problem.get("claim_id") != recorded_id:
        return recorded
    return {**obj, "problem": {**problem, "claim_id": claim_id}}


def fixture_coverage(recorded: dict, recorded_digests: dict, claims: list[ClaimRecord], outcomes: list[dict], findings: list[dict],
                     aliases: dict[str, str] | None = None) -> dict:
    """What became of each translation recorded for a task (``recorded``: the translations file's claims) in this run:
    ``served`` (the pipeline translated its claim with it and an outcome came back) or lost under one of LOST_REASONS.
    A served fixture is bound to its claim's text by the digest the translations file recorded
    (``served_with_recorded_digest``) or, when none was recorded, by claim id only (``served_by_claim_id_only``: the
    harness binds it to whatever text that id carries in this run, which may not be the sentence it was produced for).
    ``translation_sha256`` gives each recorded fixture's digest, by which an adjudication names what it judged.
    ``aliases`` (:func:`fixture_claim_ids`) gives the delivered ids each recorded id serves; without it, its own id only."""
    delivered = {c.claim_id for c in claims}
    by_id = {o["claim_id"]: o for o in outcomes}
    dropped, failed = _claims_named(findings, "INT-STALE-011"), _claims_named(findings, "INT-REQ-006")
    delivered_as: dict[str, str] = {}  # recorded id -> the delivered id it serves (its own id first)
    for did, rid in (aliases or {cid: cid for cid in recorded}).items():
        if did in delivered and (rid not in delivered_as or did == rid):
            delivered_as[rid] = did
    served: list[str] = []
    lost: dict[str, list[str]] = {k: [] for k in LOST_REASONS}
    for cid in sorted(recorded):
        did = delivered_as.get(cid)
        o = by_id.get(did) if did is not None else None
        if did is None:
            lost["matching_no_delivered_claim"].append(cid)
        elif o is not None and o.get("stale_fixture_refused"):
            lost["refused_stale"].append(cid)
        elif o is not None and o["translation_status"] == TranslationStatus.NOT_ELIGIBLE.value:
            lost["not_eligible"].append(cid)
        elif o is not None:
            served.append(cid)
        elif did in dropped:
            lost["dropped_by_channel"].append(cid)
        elif did in failed:
            lost["failed_internally"].append(cid)
        else:
            lost["no_outcome"].append(cid)
    return {"recorded": len(recorded), "served": served, "lost": {k: v for k, v in lost.items() if v}, "lost_count": sum(len(v) for v in lost.values()),
            "served_with_recorded_digest": [cid for cid in served if cid in recorded_digests],
            "served_by_claim_id_only": [cid for cid in served if cid not in recorded_digests],
            "translation_sha256": {cid: fixture_sha256(v) for cid, v in sorted(recorded.items())}}


def round_fixture_coverage(records: list[dict], translations: dict[str, dict]) -> dict:
    """Fixture coverage of the round: every translations file's fixtures, from its genuine record's coverage; a file
    whose report was not delivered (no coverage on its genuine record, or no genuine record) loses every fixture under
    ``report_not_delivered``."""
    covered = {r["file"]: r["fixture_coverage"] for r in records if r["variant"] == "genuine" and r.get("fixture_coverage")}
    out = {"recorded": 0, "served": 0, "lost": 0, "lost_by_reason": {k: 0 for k in LOST_REASONS}, "served_with_recorded_digest": 0, "served_by_claim_id_only": 0,
           "by_file": {}}
    for stem, tr in sorted(translations.items()):
        n = len(tr.get("claims") or {})
        cov = covered.get(f"{stem}.json")
        if cov is None:
            cov = {"recorded": n, "served": [], "lost": {"report_not_delivered": sorted(tr.get("claims") or {})}, "lost_count": n,
                   "served_with_recorded_digest": [], "served_by_claim_id_only": []}
        out["recorded"] += cov["recorded"]
        out["served"] += len(cov["served"])
        out["lost"] += cov["lost_count"]
        for k, ids in cov["lost"].items():
            out["lost_by_reason"][k] += len(ids)
        out["served_with_recorded_digest"] += len(cov["served_with_recorded_digest"])
        out["served_by_claim_id_only"] += len(cov["served_by_claim_id_only"])
        out["by_file"][f"{stem}.json"] = {"recorded": cov["recorded"], "served": len(cov["served"]), "lost": {k: v for k, v in cov["lost"].items() if v}}
    out["lost_by_reason"] = {k: v for k, v in out["lost_by_reason"].items() if v}
    out["definition"] = ("recorded translations (translations/*.json) this run served, i.e. the pipeline translated their claims with them, against "
                         "those it could not use, by reason; a served translation without a recorded claim-text digest is bound by claim id only")
    return out


def load_adjudications(round_dir: Path) -> dict | None:
    """The round's adjudications of translation fidelity (``<round>/adjudications/translation_fidelity.json``), or None.

    The file is a list of judgments, or ``{"adjudicator": "...", "judgments": [...]}``. A judgment names the translation
    it judged and says whether it is faithful to the claim:
    ``{"file": "hi-t13.json" (or "task_id"/"task": the task id), "claim_id": "h1.4", "verdict": "faithful" | "unfaithful"
    ('F'/'U' are accepted), "cause": optional, "translation_sha256": optional digest of the fixture judged (``fixture_sha256``),
    "claim_text_sha256": optional digest of the claim text judged}``. A judgment is applied to this run's outcome only when
    the same recorded translation was served for that claim and every digest it carries matches (``adjudicate``)."""
    path = round_dir / ADJUDICATIONS_FILE
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    judgments = data.get("judgments", []) if isinstance(data, dict) else data
    return {"source": str(ADJUDICATIONS_FILE), "adjudicator": data.get("adjudicator") if isinstance(data, dict) else None, "judgments": list(judgments)}


def adjudicate(adjudications: dict | None, records: list[dict], translations: dict[str, dict]) -> dict:
    """Translation fidelity: the round's adjudications applied to the translations this run served.

    A judgment applies to a genuine record's outcome when it names that record's file (or a task id only that record
    carries) and claim, the recorded translation for the claim was served in this run, and the digests it carries match
    the recorded fixture (``translation_sha256``) and the claim text it was served for (``claim_text_sha256``). Its
    binding says which of those it was checked against; one with neither digest is matched by file and claim id only.
    Anything else is listed under ``not_applied`` with the reason, never counted. ``faithful`` of ``adjudicated`` is the
    measure; with no adjudications the status is 'not adjudicated' and no figure is given. ``verdicts`` maps
    'file claim_id' to the verdict applied, for the claim counts."""
    base = {"definition": "translations this run served that an adjudicator judged faithful to their claim, of those judged and applicable to this run; "
                          "the adjudicator, not the engine, decides fidelity"}
    if adjudications is None:
        return {**base, "status": "not adjudicated", "source": None, "adjudicator": None, "recorded": 0, "adjudicated": 0, "faithful": 0, "unfaithful": 0,
                "rate": None, "bindings": {}, "applied": [], "not_applied": [], "verdicts": {}}
    genuine = [r for r in records if r["variant"] == "genuine"]
    by_file = {r["file"]: r for r in genuine}
    applied: list[dict] = []
    not_applied: list[dict] = []
    candidates: dict[tuple[str, str], list[tuple[dict, str]]] = {}
    for j in adjudications["judgments"]:
        claim_id = j.get("claim_id") if isinstance(j, dict) else None
        verdict = VERDICT_SPELLINGS.get(str(j.get("verdict", "")).strip().lower()) if isinstance(j, dict) else None
        name = (j.get("file") or j.get("task_id") or j.get("task")) if isinstance(j, dict) else None
        if not claim_id or verdict is None or not name:
            not_applied.append({"judgment": j, "reason": "malformed: a judgment needs a file or task id, a claim id and a verdict 'faithful' or 'unfaithful'"})
            continue
        if j.get("file"):
            file = j["file"] if str(j["file"]).endswith(".json") else f"{j['file']}.json"
            files = [file] if file in by_file else []
        else:
            files = [r["file"] for r in genuine if r.get("task_id") == name]
        if len(files) != 1:
            not_applied.append({"judgment": j, "reason": "no genuine record of this run carries that file or task" if not files else f"the task id names {len(files)} records: {files}"})
            continue
        candidates.setdefault((files[0], claim_id), []).append((j, verdict))
    verdicts: dict[str, str] = {}
    bindings = {"translation_and_claim_text": 0, "translation_only": 0, "claim_text_only": 0, "claim_id_only": 0}
    for (file, claim_id), entries in sorted(candidates.items()):
        if len({v for _j, v in entries}) > 1:
            not_applied += [{"judgment": j, "reason": "conflicting verdicts on one translation"} for j, _v in entries]
            continue
        j, verdict = entries[0]
        rec = by_file[file]
        cov = rec.get("fixture_coverage") or {}
        stem = file[:-5] if file.endswith(".json") else file
        recorded = (translations.get(stem) or {}).get("claims") or {}
        if claim_id not in recorded:
            not_applied.append({"judgment": j, "reason": "no translation is recorded for this claim"})
            continue
        if claim_id not in cov.get("served", []):
            why = next((k for k, ids in (cov.get("lost") or {}).items() if claim_id in ids), "report_not_delivered")
            not_applied.append({"judgment": j, "reason": f"the recorded translation was not served in this run ({why}: {LOST_REASONS[why]})"})
            continue
        t_ok = j.get("translation_sha256") in (None, fixture_sha256(recorded[claim_id]))
        c_ok = j.get("claim_text_sha256") in (None, (rec.get("fixture_claim_text_sha256") or {}).get(claim_id))
        if not t_ok or not c_ok:
            not_applied.append({"judgment": j, "reason": "the " + " and ".join(x for x, ok in (("translation", t_ok), ("claim text", c_ok)) if not ok)
                                + " served in this run differ from what was judged (digest mismatch)"})
            continue
        binding = {(True, True): "translation_and_claim_text", (True, False): "translation_only", (False, True): "claim_text_only",
                   (False, False): "claim_id_only"}[(j.get("translation_sha256") is not None, j.get("claim_text_sha256") is not None)]
        bindings[binding] += 1
        verdicts[f"{file} {claim_id}"] = verdict
        applied.append({"file": file, "claim_id": claim_id, "verdict": verdict, "binding": binding, **({"cause": j["cause"]} if j.get("cause") else {})})
    faithful = sum(1 for a in applied if a["verdict"] == FAITHFUL)
    return {**base, "status": "adjudicated" if applied else "no adjudication applies to this run", "source": adjudications.get("source"),
            "adjudicator": adjudications.get("adjudicator"), "recorded": len(adjudications["judgments"]), "adjudicated": len(applied), "faithful": faithful,
            "unfaithful": len(applied) - faithful, "rate": (faithful / len(applied)) if applied else None, "bindings": {k: v for k, v in bindings.items() if v},
            "applied": applied, "not_applied": not_applied, "verdicts": verdicts}


def round_claim_measures(records: list[dict], fidelity: dict) -> dict:
    """The claim counts of the round's genuine pass (each specialist's delivered report once; peer relays, syntheses and
    the mutation repeats are not counted), each stage a count of its own, with 'faithful' from the adjudications."""
    stages = ("extracted", "eligible", "attempted", "completed", "approved", "approved_resting_on_ungrounded_premises",
              "approved_resting_on_unresolved_dependencies", "release_permitted", "eligible_not_attempted")
    out: dict = {k: 0 for k in stages}
    disagreements: list[str] = []
    for r in records:
        cm = r.get("claim_measures") if r["variant"] == "genuine" else None
        if cm is None:
            continue
        for k in stages:
            out[k] += len(cm.get(k, []))
        disagreements += [f"{r['file']} {cid}" for cid in cm["eligibility_disagreements"]]
    verdicts = fidelity.get("verdicts") or {}
    attempted = {f"{r['file']} {cid}" for r in records if r["variant"] == "genuine" and r.get("claim_measures") for cid in r["claim_measures"]["attempted"]}
    approved = {f"{r['file']} {cid}" for r in records if r["variant"] == "genuine" and r.get("claim_measures") for cid in r["claim_measures"]["approved"]}
    judged = {k: v for k, v in verdicts.items() if k in attempted}
    out["faithful"] = {"faithful": sum(1 for v in judged.values() if v == FAITHFUL), "adjudicated": len(judged)} if fidelity.get("status") != "not adjudicated" else None
    out["approved_adjudicated"] = sum(1 for k in approved if k in verdicts) if out["faithful"] is not None else None
    out["approved_adjudicated_unfaithful"] = sorted(k for k in approved if verdicts.get(k) == UNFAITHFUL) if out["faithful"] is not None else None
    out["eligibility_disagreements"] = disagreements
    out["scope"] = "genuine pass: each specialist's delivered report once; peer relays, syntheses and the mutation repeats are not counted"
    out["definitions"] = {
        "extracted": "claims the current parse delivered",
        "eligible": "extracted claims the translation pipeline would translate (deterministic eligibility and the subject profile)",
        "attempted": "eligible claims the pipeline ran on with a recorded translation",
        "completed": "attempted claims shown with a definitive engine verdict on their encoding",
        "faithful": "attempted claims whose translation an adjudicator judged faithful (only where adjudicated)",
        "approved": "completed claims displayed ENTAILED with no error-level finding on the claim: what the receipt presents as verified, not a release decision",
        "approved_resting_on_unresolved_dependencies": ("approved claims whose proof relies on an ungrounded premise or on one whose task or source "
                                                        "authority no check validated"),
        "release_permitted": ("completed claims whose release assessment (release-v1) permits releasing the answer on the claim's checks, with no "
                              "error-level finding on the claim: the application's rule, kept apart from the formal status"),
    }
    return out


def _percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile of ``values`` (non-empty): the smallest value with at least ``q`` of the values at or below it."""
    s = sorted(values)
    return s[min(len(s) - 1, max(0, math.ceil(q * len(s)) - 1))]


def latency_measures(records: list[dict]) -> dict:
    """Hub processing time per transmission in this run, on this machine (genuine traffic and injected faults apart): a
    description of the run, not a stress measurement."""
    out = {}
    for name, keep in (("genuine_traffic", lambda r: r["variant"] in GENUINE_VARIANTS), ("injected_faults", lambda r: r["variant"] in INJECTED_VARIANTS)):
        ms = [r["latency_ms"] for r in records if keep(r) and isinstance(r.get("latency_ms"), (int, float))]
        out[name] = {"n": len(ms), "median_ms": statistics.median(ms), "p95_ms": _percentile(ms, 0.95), "max_ms": max(ms)} if ms else {"n": 0}
    return out


def transport_measure(records: list[dict]) -> dict:
    """The functional count, labelled for what it is: transport. Genuine traffic (genuine replies, peer relays,
    syntheses) delivered and decided, and injected faults named, each with its own count beside the total."""
    total = len(records)
    functional = sum(1 for r in records if r.get("functional"))
    gen = [r for r in records if r["variant"] in GENUINE_VARIANTS]
    inj = [r for r in records if r["variant"] in INJECTED_VARIANTS]
    return {"definition": ("a transmission is functional when the hub produced a receipt without raising, its status is consistent with the input "
                           "(genuine traffic is delivered; an injected fault is named by a finding of the expected code on the injected claim) and every "
                           "translator output was decided or rejected with diagnostics; it does not judge whether a finding is true, whether a "
                           "translation is faithful or whether an answer is better"),
            "functional": functional, "transmissions": total, "rate": (functional / total) if total else 0.0,
            "genuine_traffic": {"functional": sum(1 for r in gen if r.get("functional")), "total": len(gen),
                                "by_variant": {v: sum(1 for r in gen if r["variant"] == v) for v in GENUINE_VARIANTS}},
            "injected_faults": {"functional": sum(1 for r in inj if r.get("functional")), "total": len(inj)}}


def run_qualifications(coverage: dict, fidelity: dict) -> list[dict]:
    """Why this run's translation figures cannot stand for the recorded round: expected translations lost, served
    translations bound by claim id only, adjudications that could not be applied. Empty when none applies."""
    out = []
    if coverage["lost"]:
        reasons = "; ".join(f"{n} {LOST_LABELS[k]}" for k, n in coverage["lost_by_reason"].items())
        out.append({"code": "TRANSLATIONS_LOST", "message": (f"{coverage['lost']} of {coverage['recorded']} recorded translations were not served in this run ({reasons}); "
                                                             f"translation outcomes cover the {coverage['served']} served, so this run is not a translation "
                                                             "regression over the recorded round")})
    if coverage["served_by_claim_id_only"]:
        out.append({"code": "FIXTURES_UNBOUND", "message": (f"{coverage['served_by_claim_id_only']} of the {coverage['served']} served translations carry no recorded "
                                                            "claim-text digest: each is bound to the text its claim id carries in this run, which may not be the "
                                                            "sentence it was produced for")})
    if fidelity.get("not_applied"):
        out.append({"code": "ADJUDICATIONS_NOT_APPLIED", "message": (f"{len(fidelity['not_applied'])} of {fidelity['recorded']} adjudications do not apply to this "
                                                                     f"run (see translation_fidelity.not_applied); fidelity is measured on the {fidelity['adjudicated']} applied")})
    return out


def round_measures(records: list[dict], translations: dict[str, dict], adjudications: dict | None) -> dict:
    """results.json ``metrics``: transport, fixture coverage, translation fidelity, the claim counts and latency, each
    with its own definition and denominator, and the qualifications they raise."""
    coverage = round_fixture_coverage(records, translations)
    fidelity = adjudicate(adjudications, records, translations)
    return {"note": "separate measures, each with its own denominator; none is combined with another into one rate",
            "transport": transport_measure(records), "fixture_coverage": coverage, "translation_fidelity": fidelity,
            "claims": round_claim_measures(records, fidelity), "latency": latency_measures(records),
            "cost": "no translation provider was called (recorded fixtures only)", "qualifications": run_qualifications(coverage, fidelity)}


def _pct(n: int, d: int) -> str:
    return f"{n / d:.1%}" if d else "n/a"


def measure_lines(m: dict) -> list[str]:
    """summary.md's Measures section: one line per measure, each with its own denominator."""
    t, cov, fid, cl, lat = m["transport"], m["fixture_coverage"], m["translation_fidelity"], m["claims"], m["latency"]
    gv = t["genuine_traffic"]["by_variant"]
    lines = ["## Measures (each on its own denominator; none is combined with another into one rate)", ""]
    lines.append(f"- Transport (functional transmissions): {t['functional']} of {t['transmissions']} ({_pct(t['functional'], t['transmissions'])}). "
                 f"Genuine traffic delivered and decided: {t['genuine_traffic']['functional']} of {t['genuine_traffic']['total']} "
                 f"(genuine replies {gv['genuine']}, peer relays {gv['peer_relay']}, syntheses {gv['synthesis']}); injected faults named: "
                 f"{t['injected_faults']['functional']} of {t['injected_faults']['total']} mutation records. Transport says the hub delivered and decided "
                 "every transmission; it does not judge whether a finding is true, whether a translation is faithful or whether an answer is better.")
    if cov["recorded"]:
        lost = "; ".join(f"{n} {LOST_LABELS[k]}" for k, n in cov["lost_by_reason"].items())
        lines.append(f"- Fixture coverage (recorded translations served in this run): {cov['served']} of {cov['recorded']} served; "
                     f"NOT SERVED: {cov['lost']}{' (' + lost + ')' if lost else ''}. Of the {cov['served']} served, {cov['served_with_recorded_digest']} "
                     f"were bound to a recorded claim-text digest and {cov['served_by_claim_id_only']} by claim id only.")
    else:
        lines.append("- Fixture coverage (recorded translations served in this run): no translation is recorded for this round (no translations/*.json); "
                     "no translation outcome is expected.")
    if fid["status"] == "not adjudicated":
        lines.append(f"- Translation fidelity (faithful translations where adjudicated): not adjudicated; the round has no {ADJUDICATIONS_FILE.as_posix()}, "
                     "so no fidelity figure applies to this run.")
    else:
        by = ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in fid["bindings"].items()) or "none"
        lines.append(f"- Translation fidelity (faithful translations where adjudicated): {fid['faithful']} of {fid['adjudicated']} adjudicated translations "
                     f"served in this run were judged faithful ({_pct(fid['faithful'], fid['adjudicated'])}); {fid['recorded']} adjudications recorded"
                     f"{' by ' + str(fid['adjudicator']) if fid.get('adjudicator') else ''}, {len(fid['not_applied'])} not applicable to this run; "
                     f"bound by: {by}.")
    faithful = ": not adjudicated" if cl["faithful"] is None else f" {cl['faithful']['faithful']} of {cl['faithful']['adjudicated']} adjudicated"
    false_approvals = "" if cl["faithful"] is None else (f"; {len(cl['approved_adjudicated_unfaithful'])} of the {cl['approved_adjudicated']} adjudicated approved "
                                                         f"claims were judged unfaithful{': ' + ', '.join(cl['approved_adjudicated_unfaithful']) if cl['approved_adjudicated_unfaithful'] else ''}")
    lines.append(f"- Claims (genuine pass, each delivered claim once): extracted {cl['extracted']}; eligible for translation {cl['eligible']}; "
                 f"attempted {cl['attempted']}; completed (a definitive verdict displayed) {cl['completed']}; faithful{faithful}; approved (displayed ENTAILED "
                 f"with no error-level finding on the claim; not a release decision) {cl['approved']}, of which {cl['approved_resting_on_ungrounded_premises']} "
                 f"rest on at least one ungrounded premise and {cl.get('approved_resting_on_unresolved_dependencies', 0)} on at least one unresolved "
                 f"dependency (ungrounded, or authority no check validated){false_approvals}; release permitted by the release assessment (the "
                 f"application's rule, apart from the formal status) {cl.get('release_permitted', 0)}. Eligible claims with no translation attempted: "
                 f"{cl['eligible_not_attempted']}.")
    if cl["eligibility_disagreements"]:
        lines.append(f"  - the harness's eligibility rule disagrees with the pipeline's decision on: {', '.join(cl['eligibility_disagreements'])}")
    g, i = lat["genuine_traffic"], lat["injected_faults"]
    lat_text = "; ".join(f"{name} median {v['median_ms']:.0f} ms, 95th percentile {v['p95_ms']:.0f} ms, max {v['max_ms']:.0f} ms over {v['n']}"
                         for name, v in (("genuine traffic", g), ("injected faults", i)) if v["n"])
    lines.append(f"- Latency (hub processing per transmission in this run, on this machine; not a stress measurement): {lat_text or 'none recorded'}.")
    lines.append(f"- Cost: {m['cost']}.")
    for q in m["qualifications"]:
        lines.append(f"- QUALIFIED ({q['code']}): {q['message']}.")
    return lines


def title_line(round_name: str, m: dict) -> str:
    """summary.md's title, qualified when the run lost expected translations or serves them unbound."""
    cov = m["fixture_coverage"]
    parts = []
    if cov["lost"]:
        parts.append(f"{cov['lost']} of {cov['recorded']} recorded translations not served")
    if cov["served_by_claim_id_only"]:
        parts.append(f"{cov['served_by_claim_id_only']} served by claim id only")
    if m["translation_fidelity"].get("not_applied"):
        parts.append(f"{len(m['translation_fidelity']['not_applied'])} adjudications not applicable")
    return f"# Arena {round_name}" + (f" (QUALIFIED: {'; '.join(parts)})" if parts else "")


def run_round(round_dir: Path) -> dict:
    spec_dir, tr_dir, syn_dir = round_dir / "specialists", round_dir / "translations", round_dir / "syntheses"
    translations = {p.stem: json.loads(p.read_text()) for p in tr_dir.glob("*.json")} if tr_dir.exists() else {}
    syntheses = load_syntheses(syn_dir)  # the combinator's output as written: a file that is not JSON is relayed as text, never raised on
    adjudications = load_adjudications(round_dir)
    hub = RouterHub(signing_key=KEY, config=CFG)
    records: list[dict] = []
    t_all = time.perf_counter()
    items = load_items(spec_dir)
    # peer-dependent task id -> the relay relay_peer.py recorded: the document that agent read, compared below with the
    # current parse of the peer's raw text (which is what the genuine pass delivers)
    recorded_relays = load_recorded_relays(round_dir, items)
    recorded_relay_checks: list[dict] = []
    stale_relays_by_group: dict[str, list[str]] = {}  # group -> recorded relays of its reports that differ from the current parse
    channels: dict[str, object] = {}
    delivered: dict[str, object] = {}  # file stem -> AgentMessage delivered to the router for the genuine reply
    baseline: dict[str, list[dict]] = {}  # file stem -> every finding of the genuine receipt (full messages)
    baseline_constraints: dict[str, dict[str, str]] = {}  # file stem -> {constraint_id: detail} of the genuine receipt
    peer_docs: dict[str, SuppliedText] = {}
    last_in_group: dict[str, str] = {}
    # file stem -> {claim_id: sha256 of the claim text each fixture was produced for}: carried by the translations file
    # or captured from the genuine transmission, and handed to the fixture provider for every later variant
    fixture_digests: dict[str, dict[str, str]] = {stem: dict(tr.get("claim_text_sha256") or {}) for stem, tr in translations.items()}
    for it in items:
        last_in_group[group_of(it)] = it["task_id"]

    def make_verify_fn(stem: str, capture: bool, agent: str = ""):
        """Translator agent output -> fixture provider; verify eligible claims of the task ``stem`` through the real
        pipeline. With ``capture`` (the genuine pass) each fixture is bound to the claim text it is first served for. A
        fixture recorded under a bare claim id also serves the id the parsers give that claim on a multi-agent task
        (:func:`fixture_claim_ids`; ``agent`` is the task's agent)."""
        tr = translations.get(stem)
        if not tr:
            return None
        digests = fixture_digests.setdefault(stem, {})
        aliases = fixture_claim_ids(tr["claims"], agent)
        for did, rid in aliases.items():
            if did != rid and rid in digests and did not in digests:
                digests[did] = digests[rid]  # a digest recorded under the bare id binds the qualified id to the same text
        provider = FixtureTranslationProvider({did: json.dumps(obj) if not isinstance(obj, str) else obj for did, rid in aliases.items()
                                               for obj in [fixture_for_claim(tr["claims"][rid], rid, did)]},
                                              claim_text_sha256=digests)

        def verify_fn(claim, report, _t=Translator(provider), _ids=frozenset(aliases), _capture=digests if capture else None):
            if claim.claim_id not in _ids:
                return None
            if _capture is not None and claim.claim_id not in _capture:
                # the fixture was produced for the genuine text: bind it to that claim text (computed here, at verify
                # time, from the parsed report) so a re-stated claim under the same id is refused later
                _capture[claim.claim_id] = sha256_text(claim.claim_text)
            return verify_claim(claim, report, _t, config=CFG, signing_key=KEY)
        return verify_fn

    # Two passes: every genuine reply (with peer relays and the combinator's synthesis) first, then the fault
    # mutations, so a synthesis is judged against the reports actually delivered for the task, not against the
    # mutated re-statements that follow.
    for pass_kind, item in [(pk, it) for pk in ("genuine", "mutations") for it in items]:
        sp = item["_path"]
        task_id = item["task_id"]
        agent = item["agent_id"]
        group = group_of(item)
        texts = supplied(item)
        if group not in channels:
            channels[group] = hub.open_task(group_plan(items, group))
        ch = channels[group]
        plan = ch.plan
        tr = translations.get(sp.stem)
        verify_fn = make_verify_fn(sp.stem, pass_kind == "genuine", agent)
        ch.verify_claim_fn = verify_fn
        # The genuine pass always parses the raw text with the current code. A relay relay_peer.py recorded for a task
        # that depends on this one is compared with that parse after delivery (recorded_relay_checks); its payload is
        # never delivered in place of the reply, and only its original_response is used, as the dependent's document.
        recorded_here = [(dep, rel) for dep, rel in recorded_relays.items() if rel["peer_of"] == task_id]
        recorded_doc = recorded_relays[task_id]["payload"].get("original_response") if task_id in recorded_relays else None
        if pass_kind == "genuine":
            peer_rec, peer_text, _relayed = relay_from_peer(ch, items, item, delivered, sp.name, recorded_doc)
            if peer_rec is not None:
                records.append(peer_rec)
                if peer_text is not None:
                    peer_docs[task_id] = peer_text
        if task_id in peer_docs:
            texts = [*texts, peer_docs[task_id]]
        # A peer-dependent agent whose peer report never reached it through the hub has nothing to answer with: it sends
        # nothing (its peer_relay record says why), but its group's synthesis is still run and recorded below.
        answered = not item.get("peer_of") or task_id in peer_docs
        quote_texts = list(texts)  # the texts the altered quotation is chosen from (mutate) and recognised by (injection)
        variants = [("genuine", item["response_text"], "NONE")] + [(k,) + mutate(item["response_text"], k, quote_texts) for k in MUTATIONS]
        variants = [(k, t, quotation_expectation(k, e, own_texts=bool(supplied(item)), any_text=bool(texts))) for k, t, e in variants] if answered else []
        if answered and is_stem_subject(item["subject"]):  # STEM faults, only on STEM subjects (after the shared ones: their indices are unchanged)
            variants += [(k,) + stem_variant(item["response_text"], item["question"], k) for k in STEM_MUTATIONS]
        for vi, (kind, text, expected) in enumerate(variants):
            if expected == "SKIP" or (kind == "genuine") != (pass_kind == "genuine"):
                continue
            rec = {"file": sp.name, "task_id": task_id, "subject": item["subject"], "variant": kind, "expected": expected, "task_type": plan.agent_task_types.get(agent, plan.task_type)}
            t0 = time.perf_counter()
            hub_key = group if kind == "genuine" else f"{group}::{kind}"
            rec["channel"] = hub_key
            try:
                if kind != "genuine":
                    # every mutation gets its own hub task (same plan), so its receipt is that of a single delivery and never
                    # carries the supersession or stale-forward findings a re-statement on the genuine reply's channel would
                    vch = hub.open_task(plan)  # the hub registers it under plan.task_id: put the group's channel back and key this one
                    hub.channels[plan.task_id] = channels[group]
                    hub.channels[hub_key] = vch
                    vch.verify_claim_fn = verify_fn
                    channels[hub_key] = vch
                    if item.get("peer_of"):  # the peer's genuine report is delivered and forwarded on this channel too
                        peer_item = next(it for it in items if it["task_id"] == item["peer_of"])
                        pm_, _, _ = hub.dispatch(hub_key, peer_item["agent_id"], peer_item["question"], supplied(peer_item))
                        peer_payload = delivered.get(peer_item["_path"].stem)
                        # verified with the peer's own translations, as in the genuine pass, so the cross-agent pool the
                        # mutated reply is checked against holds the peer's formalizations too (not an empty peer share)
                        vch.verify_claim_fn = make_verify_fn(peer_item["_path"].stem, False, peer_item["agent_id"])
                        preply, _ = hub.receive(hub_key, pm_.message_id, SpecialistReport.model_validate(peer_payload.payload) if peer_payload is not None else peer_item["response_text"],
                                                agent_id=peer_item["agent_id"], report_id=f"rep-{peer_item['task_id']}-0")
                        vch.verify_claim_fn = verify_fn
                        _r, ptext, _m = relay_from_peer(vch, items, item, {peer_item["_path"].stem: preply} if preply is not None else {}, sp.name, recorded_doc)
                        texts = [*supplied(item), *([ptext] if ptext is not None else [])]
                m, req, rq = hub.dispatch(hub_key, agent, item["question"], texts)
                if m is None:
                    rec.update(functional=False, error=f"request rejected: {[f.code for f in rq.findings]}")
                    records.append(rec)
                    continue
                reply, rc = hub.receive(hub_key, m.message_id, text, agent_id=agent, report_id=f"rep-{task_id}-{vi}")
                if kind == "genuine" and reply is not None:
                    delivered[sp.stem] = reply
                if kind == "genuine" and recorded_here:
                    checks = [{"relayed_file": rel["file"], "peer_of": task_id, "dependent_task_id": dep, **payload_differences(rel["payload"], reply.payload if reply is not None else None)}
                              for dep, rel in recorded_here]
                    rec["recorded_relay_checks"] = checks
                    recorded_relay_checks.extend(checks)
                    stale_relays_by_group.setdefault(group, []).extend(c["relayed_file"] for c in checks if not c["identical"])
                codes = sorted({f.code for f in rc.findings} | {sf.code for sf in rc.structural_findings})
                found = [finding_dict(f) for f in rc.findings] + [finding_dict(sf) for sf in rc.structural_findings]
                # the genuine record keeps every message whole; a mutation record (many per task) cuts them to 300 characters
                keep = (lambda d: d) if kind == "genuine" else brief
                rec["findings"] = [keep(finding_dict(f)) for f in rc.findings]
                rec["subject_findings"] = [keep(finding_dict(sf)) for sf in rc.structural_findings]
                outcomes = [outcome_record(o) for o in rc.outcomes]
                stale = [o["claim_id"] for o in outcomes if o["stale_fixture_refused"]]
                internal = [o for o in rc.outcomes if o.display_status.value == "INTERNAL_ERROR" and not stale_fixture(o)] + [fc for fc in rc.formal_checks if fc.formal_status == "INTERNAL_ERROR"]
                reasons = []
                if rc.status is TransmissionStatus.REJECTED:
                    reasons.append("receipt REJECTED")
                if internal:
                    reasons.append(f"{len(internal)} INTERNAL_ERROR outcome(s) or formal check(s)")
                if kind == "genuine":
                    baseline[sp.stem] = found
                    baseline_constraints[sp.stem] = {c.constraint_id: c.detail for c in rc.constraint_results}
                else:
                    # A fault counts as named only by a finding of the expected code that names an injected claim or
                    # quotes the injected words, and that the genuine record does not already carry.
                    inj = injection(item["response_text"], kind, quote_texts, item.get("question", ""))
                    injected = injected_claim_ids(reply.payload["claims"] if reply else [], inj.markers)
                    expected_codes = SELF_REPORT_CODES if kind == "self_certification" else tuple(c for c in expected.split("|") if c != "NONE")
                    named = findings_naming_injection(found, expected_codes, inj, injected, baseline.get(sp.stem, []), task_id)
                    unexplained, absent = diff_against_baseline(found, baseline.get(sp.stem, []), inj, injected, task_id, baseline_constraints.get(sp.stem))
                    rec.update(injected_claim_ids=injected, named_by=[brief(f) for f in named], unexplained_findings=[brief(f) for f in unexplained],
                               baseline_findings_absent=[brief(f) for f in absent])
                    if expected_codes and not named:
                        # a miss, whatever its cause; when the receipt itself names the injected claims undecided, the
                        # reason quotes it (a limit of the encodings reads as one), and the record is still a failure
                        present = sorted(set(codes) & set(expected_codes))
                        undecided = undecided_on(rc, injected) if kind in STEM_MUTATIONS else []
                        if undecided:
                            rec["undecided_on_injected_claims"] = undecided
                        reasons.append(f"no {'/'.join(expected_codes)} finding names the injected claims {injected} or the injected words"
                                       + (f" ({present} present, but only for what the genuine text already carries or for other claims)" if present else "")
                                       + (f" (the receipt names the injected claims undecided: {'; '.join(undecided)}; a miss that a limit of the encodings "
                                          "leaves, counted as a miss)" if undecided else ""))
                if kind == "self_certification":
                    # The self-report must be named on the receipt (core, hand-off or subject code; checked above), must
                    # not be parroted as an error, and must not reach the recipient as a material claim.
                    if not all(f.code != "INT-SUBJ-003" or "VERIFIED" not in f.message for f in rc.findings):
                        reasons.append("the self-certification is parroted as an INT-SUBJ-003 error")
                    if any(c["materiality"] == "material" and "VERIFIED" in c["claim_text"] for c in (reply.payload["claims"] if reply else [])):
                        reasons.append("the self-certification reaches the recipient as a material claim")
                ok = not reasons
                if reasons:
                    rec["failure_reasons"] = reasons
                rec.update(functional=ok, status=rc.status.value, branch=rc.branch, codes=codes, outcomes=outcomes, stale_fixtures_refused=stale,
                           formal_checks=[(fc.constraint_id, fc.formal_status, fc.satisfied) for fc in rc.formal_checks],
                           constraints=[(c.constraint_id, c.satisfied) for c in rc.constraint_results], constraint_details={c.constraint_id: c.detail[:300] for c in rc.constraint_results}, coverage=[(c.item_id, c.addressed) for c in rc.coverage], claims=len(reply.payload["claims"]) if reply else None,
                           latency_ms=(time.perf_counter() - t0) * 1000.0, summary=rc.summary[:400])
                if kind == "genuine":
                    # how far each delivered claim went (extracted, eligible, attempted, completed, approved), each a list of its own
                    delivered_claims = SpecialistReport.model_validate(reply.payload).claims if reply is not None else []
                    rec["claim_measures"] = claim_measures(delivered_claims, outcomes, found)
                if kind == "genuine" and tr:
                    rec["fixture_claim_text_sha256"] = dict(fixture_digests.get(sp.stem, {}))
                    # fixtures recorded under claim ids this parse does not deliver are never served: say which
                    aliases = fixture_claim_ids(tr["claims"], agent)
                    delivered_ids = {c["claim_id"] for c in (reply.payload["claims"] if reply else [])}
                    rec["fixtures_matching_no_delivered_claim"] = sorted(set(tr["claims"]) - {rid for did, rid in aliases.items() if did in delivered_ids})
                    # what became of every recorded translation: served, or lost and why
                    rec["fixture_coverage"] = fixture_coverage(tr["claims"], tr.get("claim_text_sha256") or {}, delivered_claims, outcomes, found, aliases)
            except Exception as exc:  # a crash is a translator bug
                rec.update(functional=False, error=f"{type(exc).__name__}: {exc}", trace=traceback.format_exc()[-1500:])
            records.append(rec)
        if pass_kind == "genuine" and syntheses and task_id == last_in_group[group]:
            # The combinator's synthesis of the group's delivered reports: a transmission of its own, counted and judged,
            # run after the group's last member whatever happened to that member or any other (a crash, a rejection, a
            # peer report never relayed), so every group of a round that carries syntheses has exactly one synthesis
            # record; a member that was not delivered makes it a failure (synthesis_record).
            srec = synthesis_record(channels[group], items, item, group, syntheses, delivered)
            if stale_relays_by_group.get(group):
                # the combinator wrote its synthesis against the recorded parse; a finding on a claim whose role or id
                # changed since is read together with the recorded relay check
                srec["recorded_relays_differing"] = list(stale_relays_by_group[group])
            records.append(srec)
    total = len(records)
    functional = sum(1 for r in records if r.get("functional"))
    # Translation outcomes: the genuine pass verifies every eligible claim with a fixture exactly once, so its counts are
    # the distinct-claim counts (checked below over (file, claim_id)); the mutation variants repeat the same claims and
    # are totalled separately.
    genuine_counts: dict[str, int] = {}
    distinct: dict[str, set] = {}
    by_variant_outcomes: dict[str, dict[str, int]] = {}
    ungrounded_entailed = {"entailed": 0, "resting_only_on_ungrounded_premises": 0, "with_some_ungrounded_premise": 0, "resting_only_on_ungrounded_premises_claims": []}
    for r in records:
        for o in r.get("outcomes", []):
            bucket = outcome_bucket(o)
            bv = by_variant_outcomes.setdefault(r["variant"], {})
            bv[bucket] = bv.get(bucket, 0) + 1
            if r["variant"] == "genuine":
                genuine_counts[bucket] = genuine_counts.get(bucket, 0) + 1
                distinct.setdefault(bucket, set()).add((r["file"], o["claim_id"]))
                if o["display_status"] == "ENTAILED":
                    ungrounded_entailed["entailed"] += 1
                    if o.get("ungrounded_dependencies"):
                        ungrounded_entailed["with_some_ungrounded_premise"] += 1
                        if o["ungrounded_dependencies"] >= o.get("premises_relied_on", 0):
                            ungrounded_entailed["resting_only_on_ungrounded_premises"] += 1
                            ungrounded_entailed["resting_only_on_ungrounded_premises_claims"].append(f"{r['file']} {o['claim_id']}")
    all_variants: dict[str, int] = {}
    for bv in by_variant_outcomes.values():
        for k, n in bv.items():
            all_variants[k] = all_variants.get(k, 0) + n
    by_variant: dict[str, list[int]] = {}
    for r in records:
        by_variant.setdefault(r["variant"], [0, 0])
        by_variant[r["variant"]][1] += 1
        by_variant[r["variant"]][0] += 1 if r.get("functional") else 0
    out = {"round": round_dir.name, "transmissions": total, "functional": functional, "functional_rate": (functional / total) if total else 0.0,
           "by_variant": {k: {"functional": v[0], "total": v[1]} for k, v in by_variant.items()}, "wall_s": time.perf_counter() - t_all,
           "provider_dependent_translation_outcomes": {"scope": "genuine pass only: each eligible claim with a fixture once", "by_status": genuine_counts,
                                                       "distinct_claims": {k: len(v) for k, v in distinct.items()}, "distinct_claims_total": len(set().union(*distinct.values())) if distinct else 0,
                                                       "entailed_dependencies": ungrounded_entailed},
           "translation_outcomes_by_variant": by_variant_outcomes, "translation_outcomes_all_variants": all_variants,
           "displayed_non_entailed_definitive_outcomes": displayed_non_entailed_definitive(records),
           "withheld_verdicts": withheld_verdicts(records),
           "advisory_coverage_warnings": advisory_coverage(records),
           "translation_fixtures_matching_no_delivered_claim": unserved_fixtures(records),
           "genuine_receipts_with_errors": genuine_error_receipts(records),
           "genuine_with_errors": genuine_findings_summary(records),
           "recorded_relay_checks": recorded_relay_checks,
           "mutations_with_unexplained_findings": unexplained_summary(records),
           "failures": [r for r in records if not r.get("functional")], "records": records}
    # the separate measures, and the qualifications they raise (a run that lost expected translations says so)
    out["metrics"] = round_measures(records, translations, adjudications)
    out["qualifications"] = out["metrics"]["qualifications"]
    out["qualified"] = bool(out["qualifications"])
    (round_dir / "results.json").write_text(json.dumps(out, indent=2, default=str))
    lines = [title_line(round_dir.name, out["metrics"]), "",
             f"Transmissions: {total}; functional: {functional} ({out['functional_rate']:.1%}). This is the transport measure only: fixture coverage, "
             "translation fidelity and the claim counts are separate measures (below), never combined with it into one rate.", "",
             error_receipt_line(out["genuine_receipts_with_errors"]), ""]
    lines += measure_lines(out["metrics"])
    lines += ["", "| variant | functional | total |", "| --- | --- | --- |"]
    lines += [f"| {k} | {v['functional']} | {v['total']} |" for k, v in out["by_variant"].items()]
    lines += ["", "## Translation outcomes (provider-dependent; genuine pass, one outcome per eligible claim with a fixture)", ""]
    lines += [f"- {k}: {n} ({out['provider_dependent_translation_outcomes']['distinct_claims'].get(k, 0)} distinct claims)" for k, n in sorted(genuine_counts.items())] or ["- (no outcome)"]
    only_ungrounded = ungrounded_entailed["resting_only_on_ungrounded_premises_claims"]
    lines += [f"- ENTAILED verdicts resting only on ungrounded premises: {ungrounded_entailed['resting_only_on_ungrounded_premises']} of {ungrounded_entailed['entailed']}"
              + (f": {', '.join(only_ungrounded)}" if only_ungrounded else "")]
    lines += [withheld_verdict_line(out["withheld_verdicts"])]
    lines += [advisory_coverage_line(out["advisory_coverage_warnings"])]
    lines += definitive_outcome_lines(out["displayed_non_entailed_definitive_outcomes"])
    unserved = out["translation_fixtures_matching_no_delivered_claim"]
    if unserved["count"]:
        lines += [f"- translation fixtures recorded under claim ids this parse does not deliver (never served; those claims have no outcome): {unserved['count']} "
                  f"({'; '.join(f'{k}: {v}' for k, v in unserved['by_file'].items())})"]
    lines += [f"- all variants together (the same claims repeated): {all_variants}"]
    lines += ["", "## Genuine transmissions, peer relays and combinator syntheses carrying error- or warning-level findings (correct against a specialist's or the combinator's fault, or a false finding: read the message)", ""]
    for g in out["genuine_with_errors"]:
        tag = f"{g['variant']} {g['synthesis_id']}" if g.get("synthesis_id") else g["variant"]
        stale = f" (cites a report whose recorded relay {g['recorded_relays_differing']} differs from the current parse: see the recorded peer relays below)" if g.get("recorded_relays_differing") else ""
        lines.append(f"- {g['file']} [{tag}] {g['status']}: errors {g['codes']}, warnings {g['warning_codes']}{stale}")
        lines += [f"  - {f['severity']} {f['code']} {f['claim_ids']}: {f['message']}" for f in g["findings"]]
    if not out["genuine_with_errors"]:
        lines.append("(none)")
    lines += ["", "## Recorded peer relays (relayed/<task>.json) compared with the current parse of the peer's raw text (the genuine pass delivers the current parse; the recording is the dependent agent's document only)", ""]
    lines += recorded_relay_lines(out["recorded_relay_checks"]) or ["(no recorded relay)"]
    lines += ["", "## Mutations: findings beyond the genuine record that do not name the injection (a consequence of the injected words, such as a word bound crossed, or a wrong receipt: read the message)", ""]
    for u in out["mutations_with_unexplained_findings"]:
        lines.append(f"- {u['file']} [{u['variant']}] {u['status']}: injected claims {u['injected_claim_ids']}")
        lines += [f"  - {f['severity']} {f['code']} {f['claim_ids']}: {f['message']}" + (f" (genuine record: {f['baseline_message']})" if f.get("baseline_message") else "")
                  + (f" (genuine record: {f.get('genuine_constraint')}; the mutation added {f['words_added']} words)" if "words_added" in f else "") for f in u["unexplained"]]
        lines += [f"  - lost from the genuine record: {f['severity']} {f['code']} {f['claim_ids']}: {f['message']}" for f in u["absent"]]
        if u["unexplained_info"]:
            lines.append(f"  - info-level: {u['unexplained_info']}")
    if not out["mutations_with_unexplained_findings"]:
        lines.append("(none)")
    lines += ["", "## Failures", ""] + ([f"- {r['file']} [{r['variant']}]: {'; '.join(([r['error']] if r.get('error') else []) + (r.get('failure_reasons') or [])) or ('status ' + str(r.get('status')) + ' codes ' + str(r.get('codes')))}" for r in out["failures"]] or ["(none)"])
    (round_dir / "summary.md").write_text("\n".join(lines))
    return out


def main(argv: list[str] | None = None) -> int:
    """Run one round and print its measures. Exit status 0, or 1 with ``--fail-on-qualification`` when the run is
    qualified (expected translations lost, served translations bound by claim id only, or adjudications that do not
    apply), so a translation-regression run fails instead of reporting figures for a different set of translations."""
    ap = argparse.ArgumentParser(description="Feed a recorded arena round through the hub and write results.json and summary.md.")
    ap.add_argument("round_dir", type=Path, help="the round directory (specialists/, translations/, syntheses/, relayed/, adjudications/)")
    ap.add_argument("--fail-on-qualification", action="store_true",
                    help="exit with status 1 when the run is qualified, for a translation-regression run that must use every recorded translation")
    args = ap.parse_args(argv)
    rd = args.round_dir.resolve()
    res = run_round(rd)
    print(json.dumps({k: res[k] for k in ("round", "transmissions", "functional", "functional_rate", "by_variant", "provider_dependent_translation_outcomes", "translation_outcomes_all_variants", "wall_s")}, indent=2))
    print("failures:", len(res["failures"]))
    ge = res["genuine_receipts_with_errors"]
    print("genuine transmissions, peer relays and syntheses with errors or warnings:", len(res["genuine_with_errors"]), "| mutation records with unexplained findings:", len(res["mutations_with_unexplained_findings"]))
    print(f"genuine records with an error-level finding: {ge['with_error_findings']} of {ge['genuine_records']}, {ge['with_error_findings_counted_functional']} counted functional (the rate does not judge whether a finding is true)",
          "| definitive verdicts other than ENTAILED displayed on genuine claims:", len(res["displayed_non_entailed_definitive_outcomes"]))
    print("recorded peer relays differing from the current parse:", sum(1 for c in res["recorded_relay_checks"] if not c["identical"]), "of", len(res["recorded_relay_checks"]))
    print("\n".join(line for line in measure_lines(res["metrics"]) if line))
    print("results written to", rd / "results.json", "and", rd / "summary.md")
    if res["qualified"] and args.fail_on_qualification:
        print("FAILED: the run is qualified (--fail-on-qualification):", ", ".join(q["code"] for q in res["qualifications"]))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
