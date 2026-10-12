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
  through group_plan() and writes <round>/relayed/<task_id>.json, the only thing the peer-dependent agent may read.
  A re-run never delivers that recorded payload in place of the peer task's reply: the genuine pass parses the raw
  response_text with the code as it stands, like every other task, so a fix to a parser shows on the re-run's receipts.
  The recording is used only for the document the peer-dependent agent read (peer:<task_id> is its original_response),
  and each genuine record of a peer task carries ``recorded_relay_checks``: whether the recorded payload equals the
  current parse (created_at aside) and, when it does not, the payload fields and the claims that differ, with both
  values. results.json (``recorded_relay_checks``) and summary.md list every check, so a receipt that differs from the
  recorded relay is never read as the receipt the agent was shown.
Outputs: <round>/results.json and <round>/summary.md

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

Functional-rate definition (deterministic): a transmission counts as functional when the
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
reason, E112 circular encoding) or an encoding the translation pipeline rejected before the engine ran (E112 circular,
'stated precision': an exact equality to a rounded figure). A translation fixture recorded under a claim id the current parse does not deliver is never served; each
genuine record names such fixtures (``fixtures_matching_no_delivered_claim``) and results.json and summary.md total them
(``translation_fixtures_matching_no_delivered_claim``), so a smaller outcome count is not read as fewer eligible claims.
"""
from __future__ import annotations

import json
import re
import sys
import time
import traceback
import unicodedata
from pathlib import Path
from typing import NamedTuple

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.runner import ungrounded_dependencies, unverified_dependencies
from epinoic_logic.engine.statuses import DEFINITIVE, VerificationStatus
from epinoic_logic.integrity import AgentRole, LedgerEntry, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.translate.contracts import ClaimVerificationOutcome, SpecialistReport, SuppliedText, TranslationStatus, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

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


def injection(text: str, kind: str, texts=()) -> Injection:
    """How ``mutate(text, kind, texts)``'s injection is recognised on a receipt. For altered_quotation the marker is the
    altered quotation; for self_certification (appended as a paragraph of its own) a finding may also name its place."""
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
    """Receive the peer task's genuine reply, relay the delivered report to the requesting agent and write
    <round>/relayed/<task_id>.json: the delivered payload is all that agent may read of its peer."""
    items = load_items(round_dir / "specialists", include_pending=True)
    item = next(it for it in items if it["task_id"] == task_id)
    peer = item["peer_of"]
    peer_item = next(it for it in items if it["task_id"] == peer)
    group = group_of(item)
    hub = RouterHub(signing_key=KEY, config=CFG)
    plan = group_plan(items, group)
    ch = hub.open_task(plan)
    m, _req, rq = hub.dispatch(group, peer_item["agent_id"], peer_item["question"], supplied(peer_item))
    out = {"task_id": task_id, "peer_of": peer, "plan": {"task_type": plan.task_type, "agent_task_types": dict(plan.agent_task_types), "agent_subjects": dict(plan.agent_subjects)},
           "request": {"status": rq.status.value, "codes": sorted(f.code for f in rq.findings)}}
    if m is None:
        out.update(delivered=False, error="request to the peer was rejected")
    else:
        reply, rc = hub.receive(group, m.message_id, peer_item["response_text"], agent_id=peer_item["agent_id"], report_id=f"rep-{peer}-0")
        # the recipient sees what the hub attached to the delivery: every finding with its message, not just the codes
        out["peer_receipt"] = {"status": rc.status.value, "codes": sorted({f.code for f in rc.findings} | {sf.code for sf in rc.structural_findings}), "summary": rc.summary,
                               "findings": [{"code": f.code, "severity": f.severity, "message": f.message, "claim_ids": list(f.claim_ids)} for f in rc.findings],
                               "subject_findings": [{"code": sf.code, "severity": sf.severity, "message": sf.message, "claim_ids": list(sf.claim_ids), "rule_source": sf.rule_source} for sf in rc.structural_findings],
                               "constraints": [{"constraint_id": c.constraint_id, "satisfied": c.satisfied, "detail": c.detail} for c in rc.constraint_results],
                               "formal_checks": [{"check_id": fc.constraint_id, "status": fc.formal_status, "satisfied": fc.satisfied, "detail": fc.detail} for fc in rc.formal_checks]}
        rec, text, relayed = relay_from_peer(ch, items, item, {peer_item["_path"].stem: reply} if reply is not None else {}, item["_path"].name)
        out["relay"] = {k: v for k, v in rec.items() if k != "file"}
        out["delivered"] = relayed is not None
        if relayed is not None:
            out["document_id"] = text.document_id
            out["payload"] = relayed.payload  # the specialist_report/1.0 payload exactly as delivered
    (round_dir / "relayed").mkdir(exist_ok=True)
    (round_dir / "relayed" / f"{task_id}.json").write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return out


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


def group_synthesis(items: list[dict], group: str, syntheses: dict, delivered: dict, plan: WorkPlan, notes: dict | None = None):
    """The dummy combinator's synthesis for a hub task: the per-report syntheses of every delivered member of the
    group, merged, citing each delivered report (a peer exchange is one task with two reports).

    Evidence references: a synthesized claim of the syntheses format may carry ``evidence_refs`` ([{document_id,
    locator?, excerpt?}]), passed on as written. When it carries none, the claim keeps the references of its cited
    material source claims whose excerpts its text reproduces word for word (``reproduced_evidence_refs``): the
    combinator quoted the evidence, and the format had no field to cite it by. ``notes`` (when given) receives ``evidence_refs_copied``:
    {synthesized claim id: the references copied, each with its source claim}."""
    members = [it for it in items if group_of(it) == group and it["_path"].stem in delivered and it["_path"].stem in syntheses]
    if not members:
        return None
    s_claims, ledger, source_ids = [], [], []
    copied: dict[str, list[dict]] = {}
    for it in members:
        tid, syn, reply = it["task_id"], syntheses[it["_path"].stem], delivered[it["_path"].stem]
        by_id = {c["claim_id"]: c for c in reply.payload["claims"]}
        prefix = "" if len(members) == 1 else f"{tid}-"
        for i, c in enumerate(syn["claims"]):
            sid = f"{prefix}s{i}"
            cited = [x for x in c.get("source_claim_ids", []) if x in by_id] or c.get("source_claim_ids", [])
            if "evidence_refs" in c:
                refs = [dict(r) for r in c["evidence_refs"]]
            else:
                found = reproduced_evidence_refs(c["text"], cited, by_id)
                refs = [{k: r[k] for k in ("document_id", "locator", "excerpt")} for r in found]
                if found:
                    copied[sid] = found
            s_claims.append(SynthesizedClaim(claim_id=sid, text=c["text"], certainty=c.get("certainty", "established"),
                                             source_claim_ids=cited, transformation=c.get("transformation", "paraphrased"), evidence_refs=refs))
        ledger += [LedgerEntry(source_claim_ids=d["source_claim_ids"], transformation="dropped", reason=d.get("reason")) for d in syn.get("dropped", [])]
        source_ids.append(reply.payload["report_id"])
    if notes is not None:
        notes["evidence_refs_copied"] = copied
    s_text = " ".join(c.text for c in s_claims) or "(empty)"
    return Synthesis(synthesis_id=f"syn-{group}", request_id=plan.request_id, task_id=plan.task_id, combinator_agent_id="dummy-combinator", source_report_ids=source_ids,
                     claims=s_claims, ledger=ledger, text=s_text, text_sha256=sha256_text(s_text), created_at="2026-10-11T15:00:00Z")


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
        reasons.append(f"synthesis receipt {status}: the combinator's synthesis of the delivered reports was not delivered")
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
    ``evidence_refs_copied`` (group_synthesis). Never raises: a crash is recorded as a non-functional record."""
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
        relayed, rr = ch.relay("dummy-combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, synthesis)
        findings = [finding_dict(f) for f in rr.findings]
        subject = [finding_dict(sf) for sf in rr.structural_findings]
        internal_checks = sum(1 for fc in rr.formal_checks if fc.formal_status == "INTERNAL_ERROR") + sum(1 for o in rr.outcomes if o.display_status.value == "INTERNAL_ERROR")
        reasons = synthesis_failure_reasons(rr.status.value, relayed is not None, findings + subject, internal_checks, undelivered)
        rec.update(functional=not reasons, synthesis_id=synthesis.synthesis_id, source_report_ids=list(synthesis.source_report_ids), synthesized_claims=len(synthesis.claims),
                   status=rr.status.value, branch=rr.branch, delivered=relayed is not None,
                   codes=sorted({f["code"] for f in findings} | {sf["code"] for sf in subject}), findings=findings, subject_findings=subject,
                   formal_result_ids=list(rr.formal_result_ids), latency_ms=(time.perf_counter() - t0) * 1000.0, summary=rr.summary[:400])
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
           "translation_diagnostics": [d[:300] for d in t.diagnostics][:8], "stale_fixture_refused": stale_fixture(o)}
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
#: decided the result. The E-codes are the engine's (a definitive status withheld) and the translation pipeline's (an
#: encoding rejected before it is verified, ``E112: circular`` among its diagnostics); 'stated precision' is the
#: pipeline's rejection of an exact equality to a figure the specialist rounded.
WITHHELD_VERDICT_CODES = {"E108": "vacuous result (no premise used, or a counterexample over zero premises)",
                          "E110": "unasserted figure (a counterexample that only reassigns a figure no premise asserts)",
                          "E111": "unencoded reason (a counterexample that only reassigns conclusion symbols no premise mentions)",
                          "E112": "circular encoding (ENTAILED from premises that restate the conclusion: assumed, not derived)",
                          "stated precision": "stated precision (COUNTEREXAMPLE only because a rounded figure was encoded as an exact equality)"}
_WITHHELD_DIAG_RE = re.compile(r"\b(E108|E110|E111|E112)\b|\b(stated precision):")


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


def run_round(round_dir: Path) -> dict:
    spec_dir, tr_dir, syn_dir = round_dir / "specialists", round_dir / "translations", round_dir / "syntheses"
    translations = {p.stem: json.loads(p.read_text()) for p in tr_dir.glob("*.json")} if tr_dir.exists() else {}
    syntheses = {p.stem: json.loads(p.read_text()) for p in syn_dir.glob("*.json")} if syn_dir.exists() else {}
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

    def make_verify_fn(stem: str, capture: bool):
        """Translator agent output -> fixture provider; verify eligible claims of the task ``stem`` through the real
        pipeline. With ``capture`` (the genuine pass) each fixture is bound to the claim text it is first served for."""
        tr = translations.get(stem)
        if not tr:
            return None
        digests = fixture_digests.setdefault(stem, {})
        provider = FixtureTranslationProvider({cid: json.dumps(obj) if not isinstance(obj, str) else obj for cid, obj in tr["claims"].items()}, claim_text_sha256=digests)

        def verify_fn(claim, report, _t=Translator(provider), _ids=frozenset(tr["claims"]), _capture=digests if capture else None):
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
        verify_fn = make_verify_fn(sp.stem, pass_kind == "genuine")
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
                        vch.verify_claim_fn = make_verify_fn(peer_item["_path"].stem, False)
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
                    inj = injection(item["response_text"], kind, quote_texts)
                    injected = injected_claim_ids(reply.payload["claims"] if reply else [], inj.markers)
                    expected_codes = SELF_REPORT_CODES if kind == "self_certification" else tuple(c for c in expected.split("|") if c != "NONE")
                    named = findings_naming_injection(found, expected_codes, inj, injected, baseline.get(sp.stem, []), task_id)
                    unexplained, absent = diff_against_baseline(found, baseline.get(sp.stem, []), inj, injected, task_id, baseline_constraints.get(sp.stem))
                    rec.update(injected_claim_ids=injected, named_by=[brief(f) for f in named], unexplained_findings=[brief(f) for f in unexplained],
                               baseline_findings_absent=[brief(f) for f in absent])
                    if expected_codes and not named:
                        present = sorted(set(codes) & set(expected_codes))
                        reasons.append(f"no {'/'.join(expected_codes)} finding names the injected claims {injected} or the injected words"
                                       + (f" ({present} present, but only for what the genuine text already carries or for other claims)" if present else ""))
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
                if kind == "genuine" and tr:
                    rec["fixture_claim_text_sha256"] = dict(fixture_digests.get(sp.stem, {}))
                    # fixtures recorded under claim ids this parse does not deliver are never served: say which
                    rec["fixtures_matching_no_delivered_claim"] = sorted(set(tr["claims"]) - {c["claim_id"] for c in (reply.payload["claims"] if reply else [])})
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
           "translation_fixtures_matching_no_delivered_claim": unserved_fixtures(records),
           "genuine_receipts_with_errors": genuine_error_receipts(records),
           "genuine_with_errors": genuine_findings_summary(records),
           "recorded_relay_checks": recorded_relay_checks,
           "mutations_with_unexplained_findings": unexplained_summary(records),
           "failures": [r for r in records if not r.get("functional")], "records": records}
    (round_dir / "results.json").write_text(json.dumps(out, indent=2, default=str))
    lines = [f"# Arena {round_dir.name}", "", f"Transmissions: {total}; functional: {functional} ({out['functional_rate']:.1%})", "",
             error_receipt_line(out["genuine_receipts_with_errors"]), "", "| variant | functional | total |", "| --- | --- | --- |"]
    lines += [f"| {k} | {v['functional']} | {v['total']} |" for k, v in out["by_variant"].items()]
    lines += ["", "## Translation outcomes (provider-dependent; genuine pass, one outcome per eligible claim with a fixture)", ""]
    lines += [f"- {k}: {n} ({out['provider_dependent_translation_outcomes']['distinct_claims'].get(k, 0)} distinct claims)" for k, n in sorted(genuine_counts.items())] or ["- (no outcome)"]
    only_ungrounded = ungrounded_entailed["resting_only_on_ungrounded_premises_claims"]
    lines += [f"- ENTAILED verdicts resting only on ungrounded premises: {ungrounded_entailed['resting_only_on_ungrounded_premises']} of {ungrounded_entailed['entailed']}"
              + (f": {', '.join(only_ungrounded)}" if only_ungrounded else "")]
    lines += [withheld_verdict_line(out["withheld_verdicts"])]
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


if __name__ == "__main__":
    rd = Path(sys.argv[1]).resolve()
    res = run_round(rd)
    print(json.dumps({k: res[k] for k in ("round", "transmissions", "functional", "functional_rate", "by_variant", "provider_dependent_translation_outcomes", "translation_outcomes_all_variants", "wall_s")}, indent=2))
    print("failures:", len(res["failures"]))
    ge = res["genuine_receipts_with_errors"]
    print("genuine transmissions, peer relays and syntheses with errors or warnings:", len(res["genuine_with_errors"]), "| mutation records with unexplained findings:", len(res["mutations_with_unexplained_findings"]))
    print(f"genuine records with an error-level finding: {ge['with_error_findings']} of {ge['genuine_records']}, {ge['with_error_findings_counted_functional']} counted functional (the rate does not judge whether a finding is true)",
          "| definitive verdicts other than ENTAILED displayed on genuine claims:", len(res["displayed_non_entailed_definitive_outcomes"]))
    print("recorded peer relays differing from the current parse:", sum(1 for c in res["recorded_relay_checks"] if not c["identical"]), "of", len(res["recorded_relay_checks"]))
    print("results written to", rd / "results.json", "and", rd / "summary.md")
