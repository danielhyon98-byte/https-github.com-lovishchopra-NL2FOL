#!/usr/bin/env python3
"""Arena driver: feed real specialist-agent outputs through the hub and measure.

Inputs (one round directory):
  <round>/specialists/*.json   {task_id, subject, agent_id, task_type?, question, supplied_texts:[{document_id,title?,author?,text}], response_text}
  <round>/translations/*.json  optional: {report_id, claims: {claim_id: <translator JSON object>}, claim_text_sha256?: {claim_id: sha256}}
                               The optional claim_text_sha256 map (list_claims.py --json prints the digest of every claim;
                               bind_translations.py records it with each fixture when the translations are recorded) binds each
                               fixture to the claim text it was produced for; without it the harness captures the digest of each
                               fixture's claim from the genuine transmission. Either way the fixture provider refuses to serve a
                               fixture for a claim whose text changed (a mutation that alters the sentence, ids that shift when a
                               sentence is prepended), and the channel independently rejects an outcome bound to another text
                               (INT-STALE-011). Such a refusal is recorded per claim as STALE_FIXTURE_REFUSED: no verdict, and not an
                               infrastructure error. A fixture is keyed by the claim id list_claims.py prints, the id the hub
                               delivers. A STEM report's claim (and since integration gate 3 a History or English report's: 'h1.1',
                               'p1-point') has two forms of its id: 's1.2', and 's1.2@<agent>' when a report of
                               another agent delivered before it on the hub task holds 's1.2' (channel.bus.needs_qualified_ids; the
                               second STEM report of a group; a mutation, on a hub task of its own with only its peer's report before
                               it, keeps the unqualified form unless that peer holds the id). A fixture recorded
                               under either form serves that agent's claim under the other, its problem naming the delivered id
                               (fixture_for_claim) and its claim-text digest checked as any fixture's; every record names such
                               fixtures (``fixtures_served_under_other_id_form``) and fixture coverage counts them
                               (``served_under_other_id_form``). Ids a parser writes in one form only (the generic parser always
                               qualifies) are matched as written.
  <round>/syntheses/*.json     optional: {report_id?, claims:[{text, source_claim_ids, certainty, transformation, evidence_refs?}], dropped:[{source_claim_ids, reason}],
                               conflicts?:[{claim_ids, description}]}: the combinator sub-project's output format (its exported
                               instructions; list_claims.py prints it as synthesis_format). A disclosed conflict is relayed as an
                               unresolved conflict record of the synthesis (its id k<n>, the group's prefix before it in a peer group).
                               transformation is one of carried, paraphrased, merged, narrowed, generalized (integrity.contracts
                               TRANSFORMATION_MEANINGS says what each records; list_claims.py --json prints them as synthesis_format):
                               a category, never a description of the edit. The merged synthesis is relayed as the JSON the router
                               receives, so the hub's contract validation decides it: a value outside the contract (free text in
                               transformation, say), a malformed claim or a file that is not JSON is a REJECTED receipt (INT-REQ-009,
                               with INT-SYNTH-014 naming each value outside a closed vocabulary), recorded and counted as a failed
                               synthesis, never an exception that stops the round. Every field is passed on as written, the
                               citations included (an unknown claim id is the hub's to name, INT-LEDGER-001), and the relayed
                               synthesis lists the report of every delivered member of the group. A group's combined output (the
                               combinator's one answer for a peer group, list_claims.py --agent-view) is written to ONE member's
                               file; one file per member (rounds 1 to 7) is merged. Each file is also read by the combinator port's
                               published output rules (combinator_contract_problem): a file out of that contract (a control or
                               bidirectional character, a blank text or reason, a repeated citation, any key or field the contract
                               does not have) is named with its KIT-CB code and makes the synthesis record a failure, since the
                               deployed combinator refuses it before it leaves.
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
  through group_plan() and writes <round>/relayed/<task_id>.json, the only thing the peer-dependent agent may read: the
  delivered payload, its document id and the relay status (RELAYED_FILE_KEYS), never a receipt. The router's record of
  the relay (the plan, the request, the peer's delivery receipt with its findings and formal checks, the relay receipt)
  goes to <round>/router/<task_id>.json, which no agent reads and the harness does not use.
  A re-run never delivers that recorded payload in place of the peer task's reply: the genuine pass parses the raw
  response_text with the code as it stands, like every other task, so a fix to a parser shows on the re-run's receipts.
  The recording is used only for the document the peer-dependent agent read (peer:<task_id> is its original_response),
  and each genuine record of a peer task carries ``recorded_relay_checks``: whether the recorded payload equals the
  current parse (created_at aside) and, when it does not, the payload fields and the claims that differ, with both
  values. results.json (``recorded_relay_checks``) and summary.md list every check, so a receipt that differs from the
  recorded relay is never read as the receipt the agent was shown. Each check also names the recorded file's
  router-only fields (``router_fields_exposed``: keys outside RELAYED_FILE_KEYS, which a recording made before the
  router's record had its own file carries), so an answer written by an agent that could read its peer's receipt reads
  as one; it changes no count.
  <round>/adjudications/translation_fidelity.json  optional: an adjudicator's judgments of translation fidelity, one per translation
                               ({file or task_id, claim_id, verdict faithful|unfaithful, translation_sha256?, claim_text_sha256?};
                               load_adjudications). A judgment counts only for a translation this run served whose digests match.
Outputs: <round>/results.json and <round>/summary.md. ``python run_arena.py <round> [--fail-on-qualification]``: with the flag
the exit status is 1 when the run is qualified (below), so a translation-regression run that lost expected translations fails.

Replay configuration (results.json ``metrics.replay``; summary.md 'Replay configuration', in the Measures section). The replay
runs what production runs wherever a recording allows it, and names what it cannot run:
  - the task record: the claim verifier declares a ``task`` parameter, so the channel hands it the task record of the
    request each report answers (``channel.bus._accepts_task``) and the translator validates task-authority premises
    against the router's question as well as the supplied texts, as production's verifier does
    (``integration.runtime.live_verifier``). Round 8's translation-fidelity lens: the replay's two-argument verifier
    checked a task_setting or arithmetic_fact premise against the supplied texts only, never against the question, so
    seven outcomes of the round differed from what production computes for the same translations (an unverified
    dependency, an E112 withheld verdict). Each outcome
    says whether its translation was validated against a task record (``task_record_given``). ``--without-task-record``
    (``run_round(..., task_record=False)``) replays as the harness did before, for a comparison with the replays recorded
    then, and the configuration says so;
  - the binding of each fixture to its claim text: by the digest recorded with the fixture (``claim_text_sha256``,
    written when the translations are recorded: bind_translations.py), else by claim id only (FIXTURES_UNBOUND, below);
  - retries: a recorded translation is one provider output, so a retry the pipeline asks for (a rejected first attempt
    with a retryable diagnostic) is served the same output and fails the same way. It is never shown as a retry that
    ran: each outcome carries its ``attempts`` and ``retry_not_exercised``, and the configuration counts and names the
    genuine claims whose retry was not exercised (production retries with the diagnostics and a new provider output);
  - the synthesis timestamp: a synthesis is stamped when it is relayed (the relay clock, as the deployed combinator path
    stamps it), so it never precedes the reports it cites. Round 8's results audit and translation-fidelity lens: a
    timestamp fixed in the past put a time-dependent INT-HANDOFF-016 warning on every synthesis (OVS-DIV-002 in the
    overseer's audit).

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
Each is skipped when the answer has no site for it. A figure in code, in a mark annotation or on a line stating a mark is
no site; a site inside a quotation of another text is also named by INT-REQ-003 (the altered quotation the hub refutes)
and a term of a sum in brackets after its value by INT-SUBJ-004 (the STEM pack reads that sum at warning severity), the
codes the design names the fault with there (stem_mutations.py, "Sites"; round-8 clearance c1). The injection is named
when a finding of its code names a claim that carries the mutated text. An injection no finding names is a miss, whatever the reason, and is never excused: when
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
joint check left undecided with INTERNAL_ERROR), every member of the group was delivered (a member that was not is
named under ``members_not_delivered``: the router received only part of the group's reports) and every syntheses file
it was made from holds the combinator port's published output contract (a file that does not is named under
``combinator_contract`` with its KIT-CB code: the deployed combinator would have refused it). A group with no delivered
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
(``advisory_coverage_warnings``). A translation fixture recorded under a claim id the current parse does not deliver (in either form,
for a STEM id) is never served; each genuine record names such fixtures (``fixtures_matching_no_delivered_claim``) and results.json and
summary.md total them (``translation_fixtures_matching_no_delivered_claim``), so a smaller outcome count is not read as fewer eligible
claims.

Specialist revisions (design section 53 of ``overseer/docs/OVERSEER_DESIGN.md``): when the round holds ``feedback/`` (written by
``revision_feedback.py``) the revision pass (``revision_pass``) replays the genuine traffic on an audited hub of its own,
re-issues every revision request and compares it with the recorded feedback, delivers each recorded revision
(``revisions/<task>.json``) and reports each outcome in ``revisions`` (results.json) and "Specialist revisions" (summary.md),
apart from every other measure: it adds no record and moves no transport count, so the headline rate excludes it. Each
request is re-issued under the budget its recorded feedback was issued under (``replay_budgets``: the signed block's
``max_rounds``), a revision file that does not record the digest of what its specialist read fails gate
``feedback_as_read`` (``UNRECORDED_READ_FLAG``), and ``--fail-on-revision-gates`` makes a failed gate the exit status 1
(arena round 9, c2: the replay re-issued feedback issued under one round under the default of two, and the gate failed on
configuration for every revision).

Overseer agents for the delivery pass: ``--overseer-provider MODULE:FACTORY`` (``--overseer-pack ZIP``) configures them
through the overseer package's runner and verdict intake, and the pass is reported beside its withheld baseline without
them (``deliveries_baseline``, ``delivery_comparison``). Without the option the harness calls no model, and the pass says
that the overseer-selected fallback and its threshold were not exercised (``fallback_exercised``,
``fallback_not_exercised``; arena round 9, c2: all 22 decisions withheld for that reason alone, read as a test of the 90%
rule).

The overseer sub-project. The delivery pass and the revision pass are the overseer's (its transfer auditor and delivery
policy); every other pass and measure is the translator's own. Where the overseer is not installed (the translator runs
without it, as after its split: architecture review after arena round 8) the round still runs and both passes are
recorded as not run, with the reason (``OVERSEER_NOT_INSTALLED``; ``deliveries.skipped`` and ``revisions.skipped`` in
results.json, "(not run: ...)" in summary.md and on the command line), exactly as a pass switched off is: a pass not run is
never shown as run, and no transport count depends on either pass.
"""
from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import math
import re
import statistics
import sys
import time
import traceback
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stem_mutations import STEM_MUTATIONS, is_stem_subject, mutate_stem  # noqa: E402

from epinoic_logic.branches import RouterHub, default_registry
from epinoic_logic.branches.generic_parser import agent_claim_tag
# the delivery pass's hub, bound at import: a harness that replaces RouterHub in this module (overseer/scripts's contained
# run substitutes a hub carrying its own auditor) never reaches the delivery pass, which carries an auditor of its own
from epinoic_logic.branches.hub import RouterHub as _DeliveryHub
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.channel.bus import CLAIM_OUT_OF_SCOPE
from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.runner import ungrounded_dependencies, unverified_dependencies
from epinoic_logic.engine.statuses import DEFINITIVE, VerificationStatus
from epinoic_logic.integrity import AgentRole, WorkPlan
from epinoic_logic.translate.contracts import ClaimRecord, ClaimVerificationOutcome, SpecialistReport, SuppliedText, TranslationStatus, sha256_text
from epinoic_logic.translate.eligibility import decide_eligibility
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.parsing import ProviderOutputError, parse_json_object
from epinoic_logic.translate.pipeline import Translator, apply_subject_policy
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider
from epinoic_logic.translate.subjects import resolve_profile

#: The delivery pass's claim verifier, bound at import like its hub: a harness that replaces ``verify_claim`` in this
#: module (the contained harness's tampering hooks) never reaches the delivery pass.
_DELIVERY_VERIFY_CLAIM = verify_claim
#: Whether ``run_round`` runs the delivery pass. The contained harness (``overseer/scripts/ovs_harness.py``) switches it
#: off while it replaces this module's hub and verifier: its runs measure the transfer auditor, not delivery.
DELIVERY_PASS = True
#: The specialist revisions of a round (``revision_pass``; design section 53): a measure of its own, run only when the round
#: holds ``feedback/`` (and ``revisions/``). A harness may switch it off as it does the delivery pass.
REVISION_PASS = True
#: Why the delivery pass and the revision pass are not run where the overseer sub-project is not installed (module
#: docstring, "The overseer sub-project"): they are the overseer's, and the translator runs without it.
OVERSEER_NOT_INSTALLED = ("the overseer sub-project (package epinoic_overseer) is not installed: this pass is the overseer's (its transfer "
                          "auditor and delivery policy), so it was not run; the translator's passes and measures do not depend on it")


def overseer_installed() -> bool:
    """Whether the overseer package is found where this harness runs: located, never imported (an overseer that is
    installed but fails to import still fails its pass, loudly). A finder that refuses the name, or an entry for it
    without a spec, is an overseer that is not installed."""
    try:
        return importlib.util.find_spec("epinoic_overseer") is not None
    except (ImportError, ValueError):
        return False


#: Why a run fails where a pass of the overseer was not run because the overseer is not installed (round-9 clearance c2b, the
#: router fixer's handoff: every harness run of the restored environment ran without the delivery and revision measures, said only by
#: two "not run" lines, and exited 0). ``--without-overseer`` says the operator means it: recorded as a configuration, exit 0.
WITHOUT_OVERSEER_FAILURE = ("FAILED: the delivery pass and the revision pass were not run: the overseer is not installed "
                            "(run with --without-overseer to replay without it)")


def find_overseer_beside() -> Optional[str]:
    """Rule ``overseer-beside`` (the router fixer's handoff, round-9 clearance c2b): where the overseer cannot be located and the
    repository this harness lives in holds its sub-project (``overseer/src/epinoic_overseer``), that source tree is put on the path,
    as the repository's own test configuration does, so the documented ``python -I scripts/arena/run_arena.py <round>`` runs the
    overseer's passes inside the repository. It is APPENDED: an installed overseer always wins. A finder that refuses the name keeps
    refusing it (the overseer stays not installed). Returns the path put on ``sys.path``, else None. Never imports the overseer."""
    if overseer_installed():
        return None
    src = Path(__file__).resolve().parents[2] / "overseer" / "src"
    if not (src / "epinoic_overseer" / "__init__.py").is_file() or str(src) in sys.path:
        return None
    sys.path.append(str(src))
    importlib.invalidate_caches()
    return str(src)


OVERSEER_FOUND_BESIDE = find_overseer_beside()

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


def accepts_task(fn) -> bool:
    """Whether a claim verifier declares a ``task`` parameter (or ``**kwargs``), the rule the channel applies before it
    passes the task record (``channel.bus._accepts_task``): the replay passes the record on to ``verify_claim`` (or a
    harness's replacement of it) only then."""
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    return any((p.name == "task" and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)) or p.kind is p.VAR_KEYWORD for p in params)


def relay_clock() -> str:
    """The time a synthesis is relayed, as an RFC 3339 UTC timestamp to the second (the channel stamps a report the same
    way): the deployed combinator path stamps a synthesis when it is built from the delivered reports, so it never
    precedes a report it cites (INT-HANDOFF-016)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def quotation_expectation(kind: str, expected: str, *, own_texts: bool, any_text: bool, request_words: bool = False) -> str:
    """The code a quotation mutation must be named by, from what the task supplies. A task with a supplied text of its own
    refutes an invented or altered quotation: INT-REQ-003 ('not found in the supplied texts'), never only the
    unverifiable CORE-SRC-003. A task whose only supplied text is a relayed peer report keeps ``mutate``'s expectation
    (an invented quotation credited to 'the narrator' when no narrated text was supplied is unverifiable, not refuted, so
    either code; an altered quotation of the report INT-REQ-003). Without any supplied text a quotation is unverifiable
    rather than refuted: CORE-SRC-003, except an altered quotation whose every word the request holds (``request_words``,
    :func:`alters_request_words`): the request's own words are a text a quotation can alter, and the channel refutes the
    alteration against them (round-8 clearance c1, ps-t14), so INT-REQ-003, never only CORE-SRC-003 (round-9 clearance c2b:
    maa-t15's quoted label 'at least one blue', which the core pack now reads as a mention, draws no CORE-SRC-003, while the
    channel still refutes its alteration). Other mutations and a skipped one are returned unchanged."""
    if kind not in QUOTATION_MUTATIONS or expected == "SKIP":
        return expected
    if own_texts:
        return "INT-REQ-003"
    if kind == "altered_quotation" and request_words and not any_text:
        return "INT-REQ-003"
    return expected if any_text else "CORE-SRC-003"


def alters_request_words(text: str, question: str, texts=()) -> bool:
    """Whether the quotation the altered_quotation mutation changes (:func:`quotation_to_alter`) is made of the request's own
    words: ``question`` holds every word of it, as the channel's reading of the text a quotation alters reads them
    (``adapters.sources.nearest_text``, the request as one more text)."""
    from epinoic_logic.adapters.sources import nearest_text
    q = quotation_to_alter(text, texts)
    if q is None or not question:
        return False
    _near, missing = nearest_text(q[2], {"the request": SuppliedText(document_id="the request", title=None, author="router", text=question)})
    return not missing


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
    """``(mutated_text, expected codes joined by '|')`` of a STEM mutation, or ``(text, 'SKIP')`` when the answer has no site.
    The codes are the mutation's own and, after them, those that name the fault at its site by design (``site_codes``: a
    site inside a quotation of another text, INT-REQ-003; a term of a sum in brackets after its value, INT-SUBJ-004;
    stem_mutations.py, "Sites"; round-8 clearance c1, STEM-integration finding 25)."""
    inj = mutate_stem(text, question, kind)
    return (text, "SKIP") if inj is None else (inj.text, "|".join(inj.expected + tuple(c for c in inj.site_codes if c not in inj.expected)))


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


def baseline_in_form(baseline: list[dict], genuine_ids, delivered_ids, tag: str | None) -> list[dict]:
    """The genuine record's findings (``baseline``) in the id form of a mutation's delivery. The genuine pass delivers a
    group's reports on one hub task, where the hub qualifies a STEM report's claim ids with its agent's ``tag``
    (``qualification_tag``) after another agent's report holding them; a mutation has a hub task of its own and is
    delivered with the unqualified ids. Integration gate, round 2: the same genuine warning then read as unexplained on
    every mutation record of the group's second STEM report ('s1.4') and as absent from it ('s1.4@physics-specialist').
    When the genuine reply carries the qualified ids (``genuine_ids``) and the mutation's (``delivered_ids``) do not, each
    genuine finding's claim ids and message drop the tag, so ``findings_naming_injection`` and ``diff_against_baseline``
    read one claim as one claim (a changed genuine finding's ``baseline_message`` is then quoted without the tag);
    otherwise, and for every parser that writes its ids in one form, the findings are returned unchanged."""
    if not tag:
        return baseline
    suffix = "@" + tag
    if not any(cid.endswith(suffix) for cid in genuine_ids) or any(cid.endswith(suffix) for cid in delivered_ids):
        return baseline
    mark = re.compile(re.escape(suffix) + r"(?![A-Za-z0-9._-])")  # the tag itself, never the start of a longer agent's tag
    return [{**f, "claim_ids": [c[:-len(suffix)] if c.endswith(suffix) else c for c in f["claim_ids"]], "message": mark.sub("", f["message"])}
            for f in baseline]


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
    if tasks_file.exists():
        # a task's revision budget (design section 53) is the round's setting: taken from tasks.json when the specialist file
        # does not carry it (no recorded round before round 8 sets one, so their plans are unchanged)
        try:
            budgets = {t["task_id"]: t["revision_rounds"] for t in json.loads(tasks_file.read_text()) if isinstance(t, dict) and "revision_rounds" in t}
        except (ValueError, KeyError, TypeError):
            budgets = {}
        for it in items:
            if "revision_rounds" not in it and it["task_id"] in budgets:
                it["revision_rounds"] = budgets[it["task_id"]]
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
    # the revision rounds a round's tasks set (round 8: revision_rounds 1, so each flawed answer gets feedback once); a group
    # whose tasks set none has the plan it had before, budgets and digest included
    rounds = sorted({it["revision_rounds"] for it in gitems if isinstance(it.get("revision_rounds"), int) and not isinstance(it.get("revision_rounds"), bool)})
    extra = {"budgets": {"revision_rounds": rounds[0]}} if rounds else {}
    return WorkPlan(plan_id=f"plan-{group}", request_id=f"req-{group}", task_id=group, subject=primary["subject"], task_type=primary_task_type,
                    selected_agent_ids=[*agents, "dummy-combinator"], allowed_document_ids=doc_ids, agent_subjects=agent_subjects, agent_task_types=agent_task_types,
                    **extra)


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


#: The keys of <round>/relayed/<task>.json, the only file the peer-dependent agent may read of its peer: its own task id,
#: the peer task's id, whether the relay delivered, the relay's status, the document id the report is supplied as and
#: the specialist_report/1.0 payload exactly as the hub relayed it. Nothing of a receipt (findings, subject findings,
#: constraint results, formal checks, codes, summaries), the plan or the request reaches that agent: they are the
#: router's (ROUTER_RELAY_DIR). Round-7 router and envelope review: relay_peer() wrote the peer's delivery receipt,
#: every finding message included, into this file, and a dependent agent repeated a false finding (INT-SUBJ-001) to
#: the student (run1).
RELAYED_FILE_KEYS = ("task_id", "peer_of", "delivered", "relay_status", "document_id", "payload")
#: Where relay_peer() writes the router's record of a relay (<round>/router/<task>.json): the plan, the request to the
#: peer, the peer's delivery receipt and the relay's own receipt. Router-only: never supplied to an agent.
ROUTER_RELAY_DIR = "router"
#: ``relay_status`` when the hub relayed nothing: the request to the peer was rejected, the peer's reply was not
#: delivered, or the relay raised (the router record says which).
NOT_RELAYED = "NOT_RELAYED"


def relayed_document(task_id: str, peer_of: str, relay_status: str, document_id: str | None, payload: dict | None) -> dict:
    """The content of <round>/relayed/<task_id>.json (RELAYED_FILE_KEYS, nothing else): ``delivered`` is True exactly
    when a payload was relayed; ``document_id`` and ``payload`` are present only then. ``relay_status`` is the relay's
    transmission status (ACCEPTED, ACCEPTED_WITH_FINDINGS, REJECTED) or NOT_RELAYED, never shown as a delivery when
    nothing was delivered."""
    doc = {"task_id": task_id, "peer_of": peer_of, "delivered": payload is not None, "relay_status": relay_status}
    if payload is not None:
        doc.update(document_id=document_id, payload=payload)
    return doc


def relay_peer(round_dir: Path, task_id: str) -> dict:
    """Receive the peer task's genuine reply, relay the delivered report to the requesting agent and write two files:

    - <round>/relayed/<task_id>.json (``relayed_document``, RELAYED_FILE_KEYS only): the delivered payload, the document id
      it is supplied as and the relay status. It is all the peer-dependent agent may read of its peer;
    - <round>/router/<task_id>.json: the router's record (the plan as used, the request to the peer, the peer's delivery
      receipt with every finding, subject finding, constraint result and formal check, and the relay's own receipt). It
      is never supplied to an agent.

    Returns ``{"relayed": <the agent's document>, "router": <the router's record>, "relayed_file": <path>,
    "router_file": <path>}``."""
    items = load_items(round_dir / "specialists", include_pending=True)
    item = next(it for it in items if it["task_id"] == task_id)
    peer = item["peer_of"]
    peer_item = next(it for it in items if it["task_id"] == peer)
    group = group_of(item)
    hub = RouterHub(signing_key=KEY, config=CFG)
    plan = group_plan(items, group)
    ch = hub.open_task(plan)
    m, _req, rq = hub.dispatch(group, peer_item["agent_id"], peer_item["question"], supplied(peer_item))
    router = {"task_id": task_id, "peer_of": peer, "plan": {"task_type": plan.task_type, "agent_task_types": dict(plan.agent_task_types), "agent_subjects": dict(plan.agent_subjects)},
              "request": {"status": rq.status.value, "codes": sorted(f.code for f in rq.findings)}}
    payload, document_id, relay_status = None, None, NOT_RELAYED
    if m is None:
        router["error"] = "request to the peer was rejected"
    else:
        reply, rc = hub.receive(group, m.message_id, peer_item["response_text"], agent_id=peer_item["agent_id"], report_id=f"rep-{peer}-0")
        # the router, the recipient of the peer's delivery, keeps what the hub attached to it: every finding with its
        # message, not just the codes. It stays in the router's record: the dependent agent reads the payload only.
        router["peer_receipt"] = {"status": rc.status.value, "codes": sorted({f.code for f in rc.findings} | {sf.code for sf in rc.structural_findings}), "summary": rc.summary,
                                  "findings": [{"code": f.code, "severity": f.severity, "message": f.message, "claim_ids": list(f.claim_ids)} for f in rc.findings],
                                  "subject_findings": [{"code": sf.code, "severity": sf.severity, "message": sf.message, "claim_ids": list(sf.claim_ids), "rule_source": sf.rule_source} for sf in rc.structural_findings],
                                  "constraints": [{"constraint_id": c.constraint_id, "satisfied": c.satisfied, "detail": c.detail} for c in rc.constraint_results],
                                  "formal_checks": [{"check_id": fc.constraint_id, "status": fc.formal_status, "satisfied": fc.satisfied, "detail": fc.detail} for fc in rc.formal_checks]}
        rec, text, relayed = relay_from_peer(ch, items, item, {peer_item["_path"].stem: reply} if reply is not None else {}, item["_path"].name)
        router["relay"] = {k: v for k, v in rec.items() if k != "file"}
        relay_status = rec.get("status") or NOT_RELAYED
        if relayed is not None:
            payload, document_id = relayed.payload, text.document_id  # the specialist_report/1.0 payload exactly as delivered
    router.update(delivered=payload is not None, relay_status=relay_status)
    if document_id is not None:
        router["document_id"] = document_id
    relayed_rel, router_rel = f"relayed/{task_id}.json", f"{ROUTER_RELAY_DIR}/{task_id}.json"
    router["relayed_file"] = relayed_rel
    doc = relayed_document(task_id, peer, relay_status, document_id, payload)
    for rel, content in ((relayed_rel, doc), (router_rel, router)):
        (round_dir / rel).parent.mkdir(exist_ok=True)
        (round_dir / rel).write_text(json.dumps(content, indent=2, ensure_ascii=False, default=str))
    return {"relayed": doc, "router": router, "relayed_file": str(round_dir / relayed_rel), "router_file": str(round_dir / router_rel)}


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
    The hub refuses it (INT-REQ-009: a payload that is neither a report nor a synthesis); the harness never raises on it.
    ``raw`` holds the file's bytes as written (``load_syntheses``)."""


class SynthesisFile(dict):
    """A syntheses file's JSON object as the harness relays it, with the file's bytes as written (``raw``), so the
    combinator contract check reads the file as the combinator port reads a message (``combinator_contract_problem``:
    UTF-8, no repeated key, no float), not only as Python's JSON reader parsed it. It compares and serialises as the
    plain mapping it is."""
    raw: bytes | None = None


def load_syntheses(syn_dir: Path) -> dict[str, object]:
    """Every syntheses file of the round by file stem: its JSON value as written (a mapping, as a ``SynthesisFile``
    carrying the file's bytes, or whatever else the combinator wrote), or an ``UnreadableSynthesis`` holding the text
    when it is not JSON, so one malformed file never stops the round; the hub decides it when the group's synthesis is
    relayed, and the combinator contract check reads the bytes (synthesis_record)."""
    out: dict[str, object] = {}
    if not syn_dir.exists():
        return out
    for p in sorted(syn_dir.glob("*.json")):
        raw = p.read_text(encoding="utf-8", errors="replace")
        try:
            value = json.loads(raw)
        except ValueError:
            value = UnreadableSynthesis(raw)
        if isinstance(value, dict):
            value = SynthesisFile(value)
        if isinstance(value, (SynthesisFile, UnreadableSynthesis)):
            value.raw = p.read_bytes()
        out[p.stem] = value
    return out


#: The keys of a syntheses file the harness relays: the combinator's output, exactly the agent's format of the combinator
#: sub-project (its runner refuses any other key, KIT-CB-002). ``report_id`` (LEGACY_SYNTHESIS_KEYS) was written by the
#: tooling of rounds 1 to 7, before the sub-project existed; the harness ignores it.
SYNTHESIS_FILE_KEYS = ("claims", "dropped", "conflicts")
LEGACY_SYNTHESIS_KEYS = frozenset({"report_id"})
#: What the harness relays for a field a synthesized claim of a syntheses file leaves out: the defaults it has had since
#: round 1. Both lie in the port's closed vocabularies, so a default never puts a synthesis out of contract (the hub
#: still names a default certainty stronger than a cited source, INT-LEDGER-003).
SYNTHESIS_CLAIM_DEFAULTS = {"certainty": "established", "transformation": "paraphrased"}


def _contract_problem(code: str, reason: str, detail: str) -> dict:
    return {"code": code, "reason": reason, "detail": detail if len(detail) <= 300 else detail[:297] + "..."}


def _validation_where(e: dict) -> str:
    """One pydantic error as a position and a rule (``claims.0.text: string_pattern_mismatch``), never the input: a value
    error carries the port validator's own fixed sentence ('a synthesized claim cites each source claim once')."""
    where = ".".join(str(x) for x in e.get("loc", ())) or "output"
    msg = str(e.get("msg", ""))
    if e.get("type") == "value_error" and msg.startswith("Value error, "):
        return f"{where}: {msg[len('Value error, '):]}"
    return f"{where}: {e.get('type', 'invalid')}"


def combinator_contract_problem(value) -> dict | None:
    """The first rule of the combinator port's published output contract that a syntheses file breaks, as
    ``{"code", "reason", "detail"}`` (a ``KIT-CB`` code, the port's closed reason, positions and rules but never the
    combinator's text), or None when the file holds it. The file is read as the port reads a message and in the port's
    order (``integration.combinator_port.check_output``; the combinator's runner applies the same rules to its agent's
    output before anything leaves it): protocol JSON (UTF-8, no repeated key, no float, no lone surrogate) and an object
    (``KIT-CB-002``); a synthesized claim's transformation outside the closed vocabulary (``KIT-CB-003``); a key besides
    claims, dropped and conflicts (the legacy ``report_id`` aside: LEGACY_SYNTHESIS_KEYS) and the port's schema, read with
    the port's own models (``CombinatorOutput``: at least one synthesized claim; a text, a dropped entry's reason or a
    conflict's description with no visible character, or holding a control character other than a tab or a line break,
    or a bidirectional embedding, override or isolate, ``combinator_port.TEXT_PATTERN``; a source claim cited twice by one
    synthesized claim, or named twice by one conflict; a claim id outside the port's alphabet; a field of the wrong kind
    or another field; ``KIT-CB-002``); a synthesis text over the port's limit (``KIT-CB-006``). A claim's left-out
    certainty or transformation is read as the default the harness relays (SYNTHESIS_CLAIM_DEFAULTS).

    Not checked here: the request ids and the instruction pack (the file is the message's body; the harness builds the
    rest), and whether every citation names a claim the delivered reports hold (``KIT-CB-004``). In a replay a recorded
    synthesis cites the claim ids of the parse it was written against, so a citation the current parse does not deliver
    is the replay's, not the combinator's; the harness passes every citation on as written and the hub names an unknown
    one itself (INT-LEDGER-001)."""
    from pydantic import ValidationError

    from epinoic_logic.integration import combinator_port as CB
    from epinoic_logic.integration.canonical import CanonicalError, check_value, loads_strict
    raw = getattr(value, "raw", None)
    try:
        if raw is not None:
            value = loads_strict(raw)
        elif isinstance(value, UnreadableSynthesis):
            value = loads_strict(str(value))
        else:
            check_value(value)
    except CanonicalError as exc:
        return _contract_problem("KIT-CB-002", "output_not_json", f"the syntheses file is not protocol JSON ({exc})")
    if not isinstance(value, dict):
        return _contract_problem("KIT-CB-002", "output_not_object", f"the syntheses file holds a JSON {type(value).__name__}, not an object")
    claims = value.get("claims")
    if isinstance(claims, list):
        for i, c in enumerate(claims):
            if isinstance(c, dict) and "transformation" in c and c["transformation"] not in CB.VOCABULARY:
                return _contract_problem("KIT-CB-003", "transformation_unknown", f"claims[{i}].transformation is not one of {', '.join(CB.VOCABULARY)} "
                                                                                 "(a category, never a description of the edit)")
    extra = [k for k in value if k not in SYNTHESIS_FILE_KEYS and k not in LEGACY_SYNTHESIS_KEYS]
    if extra:
        return _contract_problem("KIT-CB-002", "output_invalid", f"the output has {len(extra)} key(s) besides claims, dropped and conflicts")
    body = {k: v for k, v in value.items() if k in SYNTHESIS_FILE_KEYS}
    if isinstance(claims, list):
        body["claims"] = [{**SYNTHESIS_CLAIM_DEFAULTS, **c} if isinstance(c, dict) else c for c in claims]
    message = {"schema": "epinoic.integration.combinator-output.v1", "protocol": "epinoic.integration.v1", "port_version": CB.PORT_VERSION,
               "ids": {"task_id": "arena", "request_id": "arena"}, "instruction_pack_sha256": "0" * 64, **body}
    try:
        out = CB.CombinatorOutput.model_validate(message)
    except ValidationError as exc:
        return _contract_problem("KIT-CB-002", "output_invalid", f"the output does not validate ({exc.error_count()} error(s)): "
                                 + "; ".join(_validation_where(e) for e in exc.errors()[:3]))
    size = sum(len(c.text.encode("utf-8")) for c in out.claims)
    if size > CB.MAX_OUTPUT_TEXT_BYTES:
        return _contract_problem("KIT-CB-006", "output_too_large", f"the synthesis text is {size} UTF-8 bytes, more than {CB.MAX_OUTPUT_TEXT_BYTES}")
    return None


def _as_list(value) -> list:
    return value if isinstance(value, list) else [] if value is None else [value]


#: The name of the deployed combinator port's composer of the student-facing text (``integration.combinator_port``),
#: ``student_facing_text(claim_texts) -> str``, when the port has one. Until it does, the port writes the text inline in
#: ``synthesis_payload`` as the claims' texts joined by a space.
PORT_TEXT_COMPOSER = "student_facing_text"


def student_facing_text(texts: list[str]) -> str:
    """The student-facing text of a relayed synthesis, composed from its synthesized claims' texts (in order) exactly as the
    deployed combinator port composes it, so the arena relays the text production would relay and never composes one of
    its own: the port's composer when it has one (:data:`PORT_TEXT_COMPOSER`), else the claims' texts joined by a space,
    which is how ``combinator_port.synthesis_payload`` writes it.

    Arena round 9 (c2, communication fidelity, minor): the joined text handed the student every quotation twice when the
    combinator carried a quotation claim beside the sentence that quotes it (ll-t15: '"I learned to swim ..."' and then
    'The column opens with a memory rather than an argument: "I learned to swim ..."'), and the hub names such a text
    (INT-LEDGER-017, rule duplicated-content). Since the round-9 clearance's second fix pass the deployed port composes the
    text itself (``combinator_port.student_facing_text``: such a claim is rendered only inside the sentence that quotes it),
    and the harness follows the port's composer unchanged (``test_the_arena_composes_the_student_facing_text_as_the_port_does``),
    so the arena relays the text production relays."""
    from epinoic_logic.integration import combinator_port as CB
    compose = getattr(CB, PORT_TEXT_COMPOSER, None)
    return compose(list(texts)) if callable(compose) else " ".join(texts)


def group_synthesis(items: list[dict], group: str, syntheses: dict, delivered: dict, plan: WorkPlan, notes: dict | None = None,
                    created_at: str | None = None):
    """The dummy combinator's synthesis for a hub task, as the JSON the router receives (a mapping of the synthesis/1.0
    shape), citing every delivered report of the group (a peer exchange is one task with two reports). The group's
    syntheses files are those of its delivered members: one combined output (the combinator's one answer for the whole
    group, the port's combined mode, written to ONE member's file: scripts/arena/README.md), or one file per member
    (the format of rounds 1 to 7), merged in group order. The harness never builds the contract models from what the
    combinator wrote: every field is passed on as written (the citations, the transformation, certainty and evidence
    references included) and the hub's own contract validation and ledger checks decide it when the mapping is relayed,
    so a malformed synthesis (a transformation written as free text, a claim that is not an object, a file that is not
    JSON) is a REJECTED receipt with its codes (INT-REQ-009, and INT-SYNTH-014 for a value outside a closed vocabulary),
    never an exception, and a citation of a claim no delivered report holds reaches the hub, which names it
    (INT-LEDGER-001). A member's syntheses file that is not JSON (``UnreadableSynthesis``) is what the router would
    receive for the group: its text is returned as the payload. Synthesized claim ids are the harness's (the format leaves
    them to it), and the student-facing text is composed from the claims' texts as the deployed combinator port composes
    it (``student_facing_text``); ``source_report_ids`` lists the report of every delivered member
    of the group, whichever member's file holds the output; a missing certainty or transformation keeps the defaults it
    always had (SYNTHESIS_CLAIM_DEFAULTS: "established", "paraphrased"). A member's disclosed ``conflicts`` (the
    combinator sub-project's format) become the synthesis's conflict records, ``unresolved`` with the id
    ``<prefix>k<n>`` unless the file says otherwise; a round whose syntheses disclose none relays exactly the mapping it
    always did.

    Integration gate, round 1 (combinator faults): the harness used to keep only the cited ids the member's own report
    held, whenever one of them did. An invented citation written beside a real one vanished before the hub saw it (so
    INT-LEDGER-001 never reached an arena receipt), and a combined output lost its citations of the other member's
    claims (a false INT-LEDGER-023 on the figures they carried) and listed one report only.

    Evidence references: a synthesized claim of the syntheses format may carry ``evidence_refs`` ([{document_id,
    locator?, excerpt?}]), passed on as written. When it carries none, the claim keeps the references of its cited
    material source claims whose excerpts its text reproduces word for word (``reproduced_evidence_refs``, over the
    claims of every delivered member, the file's own member's first): the combinator quoted the evidence, and the format
    had no field to cite it by. ``notes`` (when given) receives ``evidence_refs_copied``: {synthesized claim id: the
    references copied, each with its source claim}.

    ``created_at`` is the synthesis's timestamp, by default the relay clock when the synthesis is built (``relay_clock``),
    as the deployed combinator path stamps it, so it never precedes a report it cites. Round 8's results audit: a
    timestamp fixed in the past (2026-10-11) put INT-HANDOFF-016 ('synthesis created at ... precedes report ...') on
    every synthesis receipt, a warning that depended on the day of the replay."""
    reporting = [it for it in items if group_of(it) == group and it["_path"].stem in delivered]  # delivered members, in group order
    members = [it for it in reporting if it["_path"].stem in syntheses]
    if not members:
        return None
    unreadable = next((syntheses[it["_path"].stem] for it in members if isinstance(syntheses[it["_path"].stem], UnreadableSynthesis)), None)
    if unreadable is not None:
        return str(unreadable)
    # every delivered member's claims by id, the first holder of an id kept: used only to find the evidence references a
    # synthesized text reproduces (a citation is never filtered against it)
    group_claims: dict[str, dict] = {}
    for it in reporting:
        for c in delivered[it["_path"].stem].payload["claims"]:
            group_claims.setdefault(c["claim_id"], c)
    s_claims: list = []
    ledger: list = []
    conflicts: list = []
    source_ids = [delivered[it["_path"].stem].payload["report_id"] for it in reporting]
    copied: dict[str, list[dict]] = {}
    for it in members:
        tid, syn, reply = it["task_id"], syntheses[it["_path"].stem], delivered[it["_path"].stem]
        by_id = {**group_claims, **{c["claim_id"]: c for c in reply.payload["claims"]}}  # the file's own member's claims first
        prefix = "" if len(members) == 1 else f"{tid}-"
        if not isinstance(syn, dict):  # a JSON value that is no synthesis object: carried as one malformed claim, so the hub names it
            s_claims.append(syn)
            continue
        for i, c in enumerate(_as_list(syn.get("claims"))):
            if not isinstance(c, dict):
                s_claims.append(c)
                continue
            sid = f"{prefix}s{i}"
            cited = c.get("source_claim_ids")  # as written: the hub decides every citation (INT-LEDGER-001 for an unknown one)
            claim = dict(c)
            claim.update(claim_id=sid, **{k: c.get(k, v) for k, v in SYNTHESIS_CLAIM_DEFAULTS.items()})
            if "evidence_refs" not in c and isinstance(c.get("text"), str) and isinstance(cited, list):
                found = reproduced_evidence_refs(c["text"], [x for x in cited if isinstance(x, str)], by_id)
                claim["evidence_refs"] = [{k: r[k] for k in ("document_id", "locator", "excerpt")} for r in found]
                if found:
                    copied[sid] = found
            s_claims.append(claim)
        for d in _as_list(syn.get("dropped")):  # the 'dropped' list's entries are ledger entries whose transformation is 'dropped'
            ledger.append({**d, "transformation": "dropped"} if isinstance(d, dict) else d)
        for k_i, k in enumerate(_as_list(syn.get("conflicts"))):  # a disclosed contradiction: an unresolved conflict record
            conflicts.append({"conflict_id": f"{prefix}k{k_i}", "status": "unresolved", **k} if isinstance(k, dict) else k)
    if notes is not None:
        notes["evidence_refs_copied"] = copied
    s_text = student_facing_text([c["text"] for c in s_claims if isinstance(c, dict) and isinstance(c.get("text"), str)]) or "(empty)"
    out = {"synthesis_id": f"syn-{group}", "request_id": plan.request_id, "task_id": plan.task_id, "combinator_agent_id": "dummy-combinator",
           "source_report_ids": source_ids, "claims": s_claims, "ledger": ledger, "text": s_text, "text_sha256": sha256_text(s_text),
           "created_at": created_at if created_at is not None else relay_clock()}
    if conflicts:  # a round whose combinator disclosed none relays exactly the mapping it always did
        out["conflicts"] = conflicts
    return out


def load_recorded_relays(round_dir: Path, items: list[dict]) -> dict[str, dict]:
    """Peer-dependent task id -> {file, peer_of, payload, router_fields_exposed} for every relay relay_peer.py recorded as
    delivered: the payload is what that agent was shown of its peer when it answered. ``router_fields_exposed`` lists the
    recorded file's keys outside RELAYED_FILE_KEYS (a recording made before the router's record had its own file carries
    the peer's delivery receipt, the relay receipt, the plan and the request): what the dependent agent could read beyond
    its peer's report, reported with the recorded relay check, never counted."""
    out: dict[str, dict] = {}
    for it in items:
        if not it.get("peer_of"):
            continue
        rel_path = round_dir / "relayed" / f"{it['task_id']}.json"
        if rel_path.exists():
            rel = json.loads(rel_path.read_text())
            if rel.get("delivered") and rel.get("payload"):
                out[it["task_id"]] = {"file": f"relayed/{rel_path.name}", "peer_of": it["peer_of"], "payload": rel["payload"],
                                      "router_fields_exposed": sorted(k for k in rel if k not in RELAYED_FILE_KEYS)}
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
                              undelivered: list[str] | tuple = (), *, contract: list[dict] | tuple = ()) -> list[str]:
    """Why a combinator synthesis transmission is not functional (empty when it is): it was not delivered (a synthesis of
    the delivered reports is genuine traffic, so REJECTED is a failure, never re-labelled), a check on it failed
    internally (INT-SYNTH-013; a joint check undecided with INTERNAL_ERROR; ``internal_checks`` formal checks or outcomes
    of the receipt with INTERNAL_ERROR), a member of its group was not delivered through the hub (``undelivered``:
    their task ids), so the synthesis the router received covers only part of the group's reports, or a syntheses file
    it was made from is out of the combinator's published contract (``contract``: one ``combinator_contract_problem``
    per file, with its ``file``), which the combinator's runner refuses before anything leaves it, so the deployed path
    never delivers that synthesis, whatever the hub's receipt says."""
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
    for p in contract:
        reasons.append(f"{p['file']} is out of the combinator's published contract ({p['code']} {p['reason']}: {p['detail']}); the combinator's runner "
                       "refuses such an output before it leaves, so the deployed path never delivers this synthesis")
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
    genuine traffic that was not delivered, a failure. Never raises: a crash is recorded as a non-functional record.

    The deployed path lets a synthesis reach the hub only through the combinator's runner and the port's check, which
    refuse an output out of the published contract with a named ``KIT-CB`` code. Each syntheses file relayed here is read
    by the same rules (``combinator_contract_problem``); a file that breaks one is named under ``combinator_contract``
    (its file, code, reason and detail) and makes the record a failure, whatever the hub's receipt says, so the arena
    never counts as delivered a synthesis the deployed combinator would refuse (integration gate, round 1: a text holding
    a NUL, a bell and escape, or a bidirectional override, a blank reason and a repeated citation were relayed and
    counted functional). The synthesis is still relayed, so the receipt shows what the hub, the independent checker,
    does with it."""
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
        # every syntheses file the relayed synthesis was made from (those of the delivered members), read by the port's rules
        contract = [{"file": f"syntheses/{it['_path'].stem}.json", **problem} for it in members
                    if it["_path"].stem in delivered and it["_path"].stem in syntheses
                    for problem in (combinator_contract_problem(syntheses[it["_path"].stem]),) if problem is not None]
        if contract:
            rec["combinator_contract"] = contract
        relayed, rr = ch.relay("dummy-combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, synthesis)
        findings = [finding_dict(f) for f in rr.findings]
        subject = [finding_dict(sf) for sf in rr.structural_findings]
        internal_checks = sum(1 for fc in rr.formal_checks if fc.formal_status == "INTERNAL_ERROR") + sum(1 for o in rr.outcomes if o.display_status.value == "INTERNAL_ERROR")
        reasons = synthesis_failure_reasons(rr.status.value, relayed is not None, findings + subject, internal_checks, undelivered, contract=contract)
        shape = synthesis if isinstance(synthesis, dict) else {}
        if not isinstance(synthesis, dict):
            rec["synthesis_unreadable"] = "a syntheses file of the group is not JSON: its text was relayed as the payload"
        rec.update(functional=not reasons, synthesis_id=shape.get("synthesis_id", f"syn-{group}"), source_report_ids=list(shape.get("source_report_ids") or []),
                   synthesized_claims=len(shape.get("claims") or []), synthesis_created_at=shape.get("created_at"),
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


def provider_attempts(o: ClaimVerificationOutcome) -> int:
    """How many provider calls the pipeline made for the claim's translation (0 when it never asked: not eligible)."""
    p = o.translation.provider
    return int(p.attempts) if p is not None else 0


def retry_not_exercised(o: ClaimVerificationOutcome) -> bool:
    """True when the pipeline retried the claim's translation (a rejected first attempt with a retryable diagnostic) and
    the retry was served the recorded output again. A recorded translation is one provider output, and the fixture
    provider serves it on every attempt (``FixtureTranslationProvider``), so in a replay every retry is this one: the
    second attempt fails as the first did, where production would retry with the diagnostics and get a new output. The
    outcome is the first attempt's, and is reported as such, never as a retry that ran."""
    return provider_attempts(o) > 1


def outcome_record(o: ClaimVerificationOutcome) -> dict:
    """What a record keeps per claim outcome: enough to see why a claim is AMBIGUOUS and what a verdict rests on, how many
    provider calls the translation took (``attempts``; ``retry_not_exercised``: a retry served the same recorded output)
    and whether the translation was validated against a task record (``task_record_given``)."""
    t, v = o.translation, o.verification
    flags = t.interpretation.ambiguity_flags if t.interpretation is not None else []
    rec = {"claim_id": o.claim_id, "display_status": o.display_status.value, "translation_status": t.status.value,
           "ambiguity_flags": [{"code": f.code, "message": f.message[:300], "alternatives": [a[:200] for a in f.alternatives]} for f in flags],
           "translation_diagnostics": [d[:300] for d in t.diagnostics][:8], "stale_fixture_refused": stale_fixture(o),
           # the pipeline's own eligibility decision for the claim (the claim counts compare it with the harness's)
           "eligible": t.eligibility.eligible,
           "attempts": provider_attempts(o), "retry_not_exercised": retry_not_exercised(o), "task_record_given": t.task_sha256 is not None}
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
                           "W111": "unconstrained symbol, advisory (the counterexample stands; no source states the free symbols, or no premise "
                                   "links the conjunct of the judgement they stand for)"}


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
    """summary.md lines for the recorded peer relays compared with the current parse, each with the router-only fields
    its file exposed to the dependent agent, if any (RELAYED_FILE_KEYS)."""
    lines = []
    for c in checks:
        head = f"- {c['relayed_file']} ({c['peer_of']} relayed to {c['dependent_task_id']})"
        exposed = ([f"  - the recorded file also carries router-only fields the dependent agent could read beyond its peer's report: {c['router_fields_exposed']} "
                    f"(relay_peer.py now writes them to {ROUTER_RELAY_DIR}/<task>.json)"] if c.get("router_fields_exposed") else [])
        if c["identical"]:
            lines.append(f"{head}: identical to the current parse (created_at aside)")
            lines += exposed
            continue
        if not c.get("current_delivered", True):
            lines.append(f"{head}: DIFFERS: the current code did not deliver {c['peer_of']}'s reply; the recorded payload was not delivered in its place")
            lines += exposed
            continue
        lines.append(f"{head}: DIFFERS from the current parse; the genuine pass delivered the current parse and used the recording only for the document the agent read")
        lines += exposed
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


# --- one claim, two id forms: the hub's agent-qualified STEM ids ----------------------------------------------------------
#
# Integration gate, round 2 (correctness lens): a STEM report whose claim ids a report of ANOTHER agent delivered before
# it on the same hub task already holds is parsed with agent-qualified ids (channel.bus.needs_qualified_ids, integration
# gate 1): the same statement of the same answer is 's1.2' when no other agent's report on the task holds that id, and
# 's1.2@physics-specialist' after one that does (the second STEM report of a group; a mutation, delivered on a hub task
# of its own with only its peer's report before it, keeps the unqualified form unless that peer holds the id).
# list_claims.py printed the unqualified ids for every file, so a translation recorded from it was never served to the
# second report's qualified claim: verify_fn returned CLAIM_OUT_OF_SCOPE, the genuine receipt was a clean ACCEPTED with
# no outcome, and the fixture's claim-text digest was never captured, so a mutation's changed claim was served the
# genuine claim's translation. A recorded translation keyed by either form of one agent's STEM claim id now serves that
# claim, explicitly: its problem names the delivered id (``fixture_for_claim``), the claim-text digest binds it as any
# fixture, and every record and the fixture coverage name each translation served under the other form of its id. Ids
# the parser always qualifies (the generic parser's 'g1.2@economics-specialist') or never qualifies have one form: a
# fixture keyed by another form is an older parse's and stays unserved ("never re-key them by bare claim id",
# scripts/arena/README.md).


def qualification_tag(item: dict) -> str | None:
    """The tag the hub qualifies ``item``'s claim ids with when a report of another agent delivered before it on the task
    holds one of them (``generic_parser.agent_claim_tag`` of its agent), or None when its branch's parser never qualifies
    its ids on that account (only a parser that offers ``accepts_qualify_ids``, the STEM parsers' and since integration
    gate 3 the History and English parsers', is asked to: the rule ``channel.bus.needs_qualified_ids``)."""
    branch, _profile = default_registry().for_subject(item["subject"])
    if getattr(branch.parser(), "accepts_qualify_ids", False) is not True:
        return None
    return agent_claim_tag(item["agent_id"])


def other_id_form(claim_id: str, tag: str | None) -> str | None:
    """The other form the hub's rule gives one claim id of a report whose ids it may qualify with ``tag``
    (``qualification_tag``): 's1.2' for 's1.2@physics-specialist' and the reverse. None without a tag, or for an id
    qualified with another tag (another agent's claim)."""
    if not tag or not isinstance(claim_id, str):
        return None
    suffix = "@" + tag
    if claim_id.endswith(suffix):
        base = claim_id[:-len(suffix)]
        return base if base and "@" not in base else None
    return None if "@" in claim_id else claim_id + suffix


def fixture_key(claim_id: str, recorded, tag: str | None) -> str | None:
    """The recorded translation that serves the delivered claim ``claim_id``: its own id when a fixture is recorded under
    it, else the other form of the id (``other_id_form``) when one is recorded under that; None when neither is."""
    if claim_id in recorded:
        return claim_id
    other = other_id_form(claim_id, tag)
    return other if other is not None and other in recorded else None


def fixture_ids_delivered(recorded, delivered, tag: str | None) -> dict[str, str]:
    """Recorded fixture id -> the delivered claim id it serves in this run: itself when the parse delivers it, else the
    other form of the id when the parse delivers that and no fixture is recorded under it (``fixture_key`` read from the
    fixture's side). A recorded id that serves no delivered claim is absent."""
    delivered = set(delivered)
    out: dict[str, str] = {}
    for rid in recorded:
        if rid in delivered:
            out[rid] = rid
            continue
        other = other_id_form(rid, tag)
        if other is not None and other in delivered and other not in recorded:
            out[rid] = other
    return out


def served_under_other_id_form(recorded, delivered, tag: str | None) -> dict[str, str]:
    """The recorded fixtures that serve a delivered claim under the other form of their id: recorded id -> delivered id."""
    return {rid: did for rid, did in fixture_ids_delivered(recorded, delivered, tag).items() if rid != did}


def fixture_for_claim(value, recorded_id: str, claim_id: str) -> str:
    """The recorded translation ``value`` (the provider's JSON as the translations file holds it: an object, or text) as it
    is served to the delivered claim ``claim_id``, the other form of its recorded id ``recorded_id``: a copy whose problem
    names ``claim_id`` where it named ``recorded_id`` (data only: read by the pipeline's own reader, nothing evaluated,
    nothing else changed). The translation is the same one the recorded id would have been served, so a problem naming
    any other claim, or a text that is no JSON object, is served unchanged and the pipeline decides it as it would
    under the recorded id (a problem naming another claim is INVALID_FORMALIZATION)."""
    if isinstance(value, str):
        try:
            obj = parse_json_object(value)
        except ProviderOutputError:
            return value
    elif isinstance(value, dict):
        obj = json.loads(json.dumps(value))
    else:
        return json.dumps(value)
    problem = obj.get("problem")
    if isinstance(problem, dict) and problem.get("claim_id") == recorded_id:
        problem["claim_id"] = claim_id
    return json.dumps(obj)


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


def claim_measures(claims: list[ClaimRecord], outcomes: list[dict], findings: list[dict], offered=None) -> dict:
    """A genuine record's claims by how far each went, every stage a list of claim ids of its own:

    - ``extracted``: every claim the current parse delivered;
    - ``eligible``: those the translation pipeline would translate (its own decision where an outcome carries one,
      otherwise ``translation_eligible``; where both exist and disagree the claim is listed under
      ``eligibility_disagreements``);
    - ``attempted``: eligible claims the pipeline ran on (a recorded translation was offered: an outcome other than
      NOT_ELIGIBLE, or an outcome the channel dropped as stale, or a verification that raised). ``offered`` (when given:
      the claim ids the round's translations file records, the only claims the harness's verifier runs on) bounds the
      last two: the channel also names under INT-REQ-006 a material eligible claim that got no outcome (NOT_ATTEMPTED:
      the verifier returned none, as it does for a claim with no recorded translation), and that is no attempt
      (integration gate, round 1);
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
                 if (cid in by_id and by_id[cid]["translation_status"] != TranslationStatus.NOT_ELIGIBLE.value)
                 or ((cid in dropped or cid in failed) and (offered is None or cid in offered))]
    completed = [cid for cid in attempted if cid in by_id and not by_id[cid].get("stale_fixture_refused") and by_id[cid]["display_status"] in DEFINITIVE_DISPLAY]
    errors = {cid for f in findings if f["severity"] == "error" for cid in f["claim_ids"]}
    approved = [cid for cid in completed if by_id[cid]["display_status"] == VerificationStatus.ENTAILED.value and cid not in errors]
    return {"extracted": [c.claim_id for c in claims], "eligible": eligible, "attempted": attempted, "completed": completed, "approved": approved,
            "approved_resting_on_ungrounded_premises": [cid for cid in approved if by_id[cid].get("ungrounded_dependencies")],
            "approved_resting_on_unresolved_dependencies": [cid for cid in approved
                                                            if by_id[cid].get("ungrounded_dependencies") or by_id[cid].get("unverified_dependencies")],
            "release_permitted": [cid for cid in completed if by_id[cid].get("release_permitted") is True and cid not in errors],
            "eligible_not_attempted": [cid for cid in eligible if cid not in set(attempted)], "eligibility_disagreements": disagreements}


def fixture_coverage(recorded: dict, recorded_digests: dict, claims: list[ClaimRecord], outcomes: list[dict], findings: list[dict],
                     tag: str | None = None) -> dict:
    """What became of each translation recorded for a task (``recorded``: the translations file's claims) in this run:
    ``served`` (the pipeline translated its claim with it and an outcome came back) or lost under one of LOST_REASONS.
    A served fixture is bound to its claim's text by the digest the translations file recorded
    (``served_with_recorded_digest``) or, when none was recorded, by claim id only (``served_by_claim_id_only``: the
    harness binds it to whatever text that id carries in this run, which may not be the sentence it was produced for).
    ``translation_sha256`` gives each recorded fixture's digest, by which an adjudication names what it judged. Each list
    names fixtures by their recorded id; with ``tag`` (``qualification_tag`` of the task's specialist) a fixture recorded
    under one form of a STEM claim id serves the claim the parse delivers under the other (``fixture_ids_delivered``), and
    ``served_under_other_id_form`` maps each such fixture's recorded id to the delivered id it served."""
    delivered = {c.claim_id for c in claims}
    serves = fixture_ids_delivered(recorded, delivered, tag)
    by_id = {o["claim_id"]: o for o in outcomes}
    dropped, failed = _claims_named(findings, "INT-STALE-011"), _claims_named(findings, "INT-REQ-006")
    served: list[str] = []
    lost: dict[str, list[str]] = {k: [] for k in LOST_REASONS}
    for cid in sorted(recorded):
        did = serves.get(cid)  # the delivered claim the fixture serves (its own id, or the other form of a STEM id)
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
            "served_under_other_id_form": {cid: serves[cid] for cid in served if serves[cid] != cid},
            "translation_sha256": {cid: fixture_sha256(v) for cid, v in sorted(recorded.items())}}


def round_fixture_coverage(records: list[dict], translations: dict[str, dict]) -> dict:
    """Fixture coverage of the round: every translations file's fixtures, from its genuine record's coverage; a file
    whose report was not delivered (no coverage on its genuine record, or no genuine record) loses every fixture under
    ``report_not_delivered``."""
    covered = {r["file"]: r["fixture_coverage"] for r in records if r["variant"] == "genuine" and r.get("fixture_coverage")}
    out = {"recorded": 0, "served": 0, "lost": 0, "lost_by_reason": {k: 0 for k in LOST_REASONS}, "served_with_recorded_digest": 0, "served_by_claim_id_only": 0,
           "served_under_other_id_form": 0, "by_file": {}}
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
        other_form = cov.get("served_under_other_id_form") or {}
        out["served_under_other_id_form"] += len(other_form)
        out["by_file"][f"{stem}.json"] = {"recorded": cov["recorded"], "served": len(cov["served"]), "lost": {k: v for k, v in cov["lost"].items() if v},
                                          **({"served_under_other_id_form": dict(other_form)} if other_form else {})}
    out["lost_by_reason"] = {k: v for k, v in out["lost_by_reason"].items() if v}
    out["definition"] = ("recorded translations (translations/*.json) this run served, i.e. the pipeline translated their claims with them, against "
                         "those it could not use, by reason; a served translation without a recorded claim-text digest is bound by claim id only; one "
                         "recorded under one form of a STEM claim id (s1.2, or s1.2@<agent> when the hub qualified the report's ids) and served to the "
                         "claim the parse delivers under the other is counted under served_under_other_id_form")
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
        # a judgment names a translation by its recorded id (bind_adjudications.py); one that names the delivered id of a
        # translation served under the other form of its recorded id (a STEM id the hub qualified) names that translation
        other_form = (by_file[files[0]].get("fixture_coverage") or {}).get("served_under_other_id_form") or {}
        recorded_ids = (translations.get(files[0][:-5] if files[0].endswith(".json") else files[0]) or {}).get("claims") or {}
        if claim_id not in recorded_ids:
            claim_id = next((rid for rid, did in other_form.items() if did == claim_id), claim_id)
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
        # the claim counts name the claim by the id the parse delivered it under (the other form of a STEM id included)
        delivered_id = (cov.get("served_under_other_id_form") or {}).get(claim_id, claim_id)
        verdicts[f"{file} {delivered_id}"] = verdict
        applied.append({"file": file, "claim_id": claim_id, "verdict": verdict, "binding": binding, **({"cause": j["cause"]} if j.get("cause") else {}),
                        **({"delivered_claim_id": delivered_id} if delivered_id != claim_id else {})})
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


def replay_configuration(records: list[dict], coverage: dict, *, task_record: bool = True) -> dict:
    """``metrics.replay``: what this replay runs as production does and what it cannot run, each named.

    - ``task_record``: whether the claim verifier received the task record of the request each report answers (production
      does), with how many genuine outcomes' translations were validated against one;
    - ``fixture_binding``: the served translations bound to the claim text they were produced for by a recorded digest,
      and those bound by claim id only (the FIXTURES_UNBOUND qualification);
    - ``retries``: a recorded translation is one provider output, so a retry the pipeline asks for is served the same
      output (``retry_not_exercised``): the genuine claims whose retry was not exercised, by name, and the total over every
      variant. Their outcomes are first-attempt outcomes; production retries with the diagnostics and a new output;
    - ``synthesis_created_at``: syntheses are stamped when relayed (``relay_clock``)."""
    genuine = [(r, o) for r in records if r["variant"] == "genuine" for o in r.get("outcomes", [])]  # the genuine pass: each claim once
    retried = [f"{r['file']} {o['claim_id']}" for r, o in genuine if o.get("retry_not_exercised")]
    every = sum(1 for r in records for o in r.get("outcomes", []) if o.get("retry_not_exercised"))
    asked = [o for _r, o in genuine if o.get("attempts", 0) > 0]  # the translations the provider was asked for
    given, translated = sum(1 for o in asked if o.get("task_record_given")), len(asked)
    return {"note": "what this replay runs as production does, and what a recording cannot run; none of it is a measure of the hub",
            "task_record": {"passed": bool(task_record), "genuine_translations_validated_against_it": given, "genuine_translations": translated,
                            "definition": ("the claim verifier declares a task parameter, so the channel hands the translator the task record of the request "
                                           "each report answers and task-authority premises are validated against the router's question, as production does"
                                           if task_record else
                                           "NOT passed (--without-task-record): task-authority premises are validated against the supplied texts only, as in "
                                           "the replays before round 8's clearance; production passes the task record")},
            "fixture_binding": {"served_with_recorded_digest": coverage.get("served_with_recorded_digest", 0),
                                "served_by_claim_id_only": coverage.get("served_by_claim_id_only", 0),
                                "definition": ("a served translation is bound to the claim text it was produced for by the digest recorded with it "
                                               "(claim_text_sha256, written by bind_translations.py when the translations are recorded); without one it is "
                                               "bound to whatever text its claim id carries in this run (FIXTURES_UNBOUND)")},
            "retries": {"not_exercised_genuine_claims": len(retried), "claims": retried, "not_exercised_all_variants": every,
                        "definition": ("a recorded translation is one provider output: a retry the pipeline asks for (a first attempt rejected with a "
                                       "retryable diagnostic) is served the same output and fails as the first attempt did, so the outcome is the first "
                                       "attempt's; production retries with the diagnostics and a new provider output")},
            "synthesis_created_at": "the relay clock: each synthesis is stamped when it is relayed, after the reports it cites"}


def replay_line(rp: dict) -> str:
    """summary.md's line on the replay configuration (in the Measures section, after the measures)."""
    tr, fb, rt = rp["task_record"], rp["fixture_binding"], rp["retries"]
    task = (f"the task record of each request is passed to the translator, as production passes it ({tr['genuine_translations_validated_against_it']} of "
            f"{tr['genuine_translations']} genuine translations validated against it)" if tr["passed"] else
            "the task record is NOT passed to the translator (--without-task-record: task-authority premises are validated against the supplied texts "
            "only, unlike production)")
    named = f": {', '.join(rt['claims'])}" if rt["claims"] else ""
    return (f"- Replay configuration (what a recording cannot run as production does is named, never counted as run): {task}; "
            f"{fb['served_with_recorded_digest']} served translations bound to a recorded claim-text digest, {fb['served_by_claim_id_only']} by claim id "
            f"only; retries NOT exercised (a recorded translation is one output, so a retry is served the same output and the outcome is the first "
            f"attempt's) on {rt['not_exercised_genuine_claims']} genuine claim(s){named} ({rt['not_exercised_all_variants']} over every variant); "
            "syntheses stamped at relay time.")


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
                                                            "sentence it was produced for (record the digests with the translations when they are recorded: "
                                                            "scripts/arena/bind_translations.py)")})
    if fidelity.get("not_applied"):
        out.append({"code": "ADJUDICATIONS_NOT_APPLIED", "message": (f"{len(fidelity['not_applied'])} of {fidelity['recorded']} adjudications do not apply to this "
                                                                     f"run (see translation_fidelity.not_applied); fidelity is measured on the {fidelity['adjudicated']} applied")})
    return out


def round_measures(records: list[dict], translations: dict[str, dict], adjudications: dict | None, *, task_record: bool = True) -> dict:
    """results.json ``metrics``: transport, fixture coverage, translation fidelity, the claim counts and latency, each
    with its own definition and denominator, the qualifications they raise, and the replay's configuration
    (``replay_configuration``: what it runs as production does and what it cannot)."""
    coverage = round_fixture_coverage(records, translations)
    fidelity = adjudicate(adjudications, records, translations)
    return {"note": "separate measures, each with its own denominator; none is combined with another into one rate",
            "transport": transport_measure(records), "fixture_coverage": coverage, "translation_fidelity": fidelity,
            "claims": round_claim_measures(records, fidelity), "latency": latency_measures(records),
            "cost": "no translation provider was called (recorded fixtures only)", "qualifications": run_qualifications(coverage, fidelity),
            "replay": replay_configuration(records, coverage, task_record=task_record)}


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
        other = cov.get("served_under_other_id_form") or 0
        named = "; ".join(f"{f}: " + ", ".join(f"{rid} as {did}" for rid, did in v["served_under_other_id_form"].items())
                          for f, v in (cov.get("by_file") or {}).items() if v.get("served_under_other_id_form"))
        lines.append(f"- Fixture coverage (recorded translations served in this run): {cov['served']} of {cov['recorded']} served; "
                     f"NOT SERVED: {cov['lost']}{' (' + lost + ')' if lost else ''}. Of the {cov['served']} served, {cov['served_with_recorded_digest']} "
                     f"were bound to a recorded claim-text digest and {cov['served_by_claim_id_only']} by claim id only."
                     + (f" Served to their claim under the other form of its STEM claim id (the hub qualifies a report's ids with its agent when "
                        f"another agent's report delivered before it on the task holds them): {other} ({named})." if other else ""))
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
    if m.get("replay"):
        lines.append(replay_line(m["replay"]))
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


# ============================================================================================ the delivery pass
#: The overseer secret of the delivery pass's own auditor (32 bytes or more, unlike the engine key).
DELIVERY_SECRET = b"arena-delivery-pass-overseer-secret-0123456789"
#: The translator versions of hand-built translations the delivery pass's auditor is told about (as the contained run).
DELIVERY_HAND_BUILT = ("test", "harness")
#: Every engine key id the hub's own components sign under, each with the arena's one engine key (as the contained
#: harness declares them, overseer/scripts/ovs_harness.py ENGINE_KEY_IDS): the hub's channels ("hub", RouterHub's key
#: id), a channel opened on its own ("channel", TranslatorChannel's), the claim verifier ("default", the engine's key id
#: when none is named) and the cross-agent consistency and synthesis checks ("integrity", integrity.cross_check).
#: Integration gate, round 1: the keyring declared only "hub" and "default", so every result the cross-agent check
#: signed (an INT-CONFLICT-004 warning's, say) was audited as untrusted (OVS-RES-003) and its answer excluded.
DELIVERY_ENGINE_KEY_IDS = ("hub", "channel", "default", "integrity")


def _delivery_auditor():
    """The delivery pass's transfer auditor: its own key ring (the engine key under every key id the hub's components
    sign under, DELIVERY_ENGINE_KEY_IDS) and inline replay, so every decision reads a complete signed task audit."""
    from epinoic_overseer import EngineKey, KeyRing, TransferAuditor
    keyring = KeyRing({key_id: EngineKey(KEY) for key_id in DELIVERY_ENGINE_KEY_IDS}, DELIVERY_SECRET)
    return TransferAuditor(keyring, replay_mode="inline", eager=True, hand_built_translators=DELIVERY_HAND_BUILT, inline_final_release=True)


#: The keys of ``delivery_overseer`` that ``DeliveryPolicy`` takes; ``label`` (what the records name the overseer agents by)
#: is the harness's own.
DELIVERY_POLICY_KEYS = ("pack", "provider_factory", "pool_config", "router", "advisor")
_PROVIDER_SPEC_RE = re.compile(r"(?P<module>[A-Za-z_][A-Za-z0-9_]{0,99}(?:\.[A-Za-z_][A-Za-z0-9_]{0,99}){0,20}):(?P<attr>[A-Za-z_][A-Za-z0-9_]{0,99})")


def load_provider_factory(spec: str):
    """The provider factory ``MODULE:FACTORY`` names (``agent_id -> completion provider``, the factory the delivery policy
    builds its overseer agents' pool from): the operator's own code, imported by its dotted module name, never text from a
    round or an agent. A malformed name, a module that cannot be imported or an attribute that is not callable is a
    ValueError or ImportError, before any pass runs."""
    m = _PROVIDER_SPEC_RE.fullmatch(spec or "")
    if m is None:
        raise ValueError(f"expected MODULE:FACTORY (a dotted module name and a callable in it), not {spec!r}")
    factory = getattr(importlib.import_module(m.group("module")), m.group("attr"), None)
    if not callable(factory):
        raise ValueError(f"{spec} is not callable")
    return factory


def delivery_overseer_config(provider_spec: str, pack_path: Path | None = None) -> dict:
    """The delivery pass's overseer agents for ``--overseer-provider``: the provider factory ``provider_spec`` names
    (``load_provider_factory``) and where the knowledge pack comes from (``pack_zip``): the exported zip ``pack_path``, or,
    by default, the installed pack exported to a temporary directory and loaded from its zip, as the deployed policy loads
    it (``DeliveryPolicy(pack=load_pack(<zip>), provider_factory=...)``). The pack is loaded by ``delivery_pass`` itself
    (the harness imports the overseer only inside its delivery pass). The agents then run through the package's runner
    and verdict intake, so every verdict the pass counts is runner-attested; the records name the provider by
    ``provider_spec`` (``label``). A name that is not a callable factory, or a pack file that does not exist, is refused
    here, before any pass runs; a pack that does not load is the pass's own named error."""
    if not overseer_installed():
        raise ImportError(OVERSEER_NOT_INSTALLED)
    factory = load_provider_factory(provider_spec)
    if pack_path is not None and not Path(pack_path).is_file():
        raise ValueError(f"no exported pack at {pack_path}")
    return {"provider_factory": factory, "label": provider_spec, "pack_zip": Path(pack_path) if pack_path is not None else None}


def _withheld_why(label: str | None, wording_by_cause: dict) -> str | None:
    """The cause a withheld decision's label states (``wording_by_cause``: the policy's fixed wording per cause,
    ``no_candidate``, ``no_accuracy``, ``no_acceptable``, ``below_threshold`` ...), or None when the label states none."""
    for kind, wording in (wording_by_cause or {}).items():
        if label and wording in label:
            return kind
    return None


def fallback_accounting(tasks: list[dict], configured: bool) -> dict:
    """Whether the delivery pass exercised the overseer-selected fallback (the founder's rule: deliver the most accurate
    acceptable candidate only above the threshold, labelled honestly), counted from its records: the decisions whose
    overseer stage ran and established an accuracy (no time-out, no error), the overseer-selected ones and the withheld
    ones by cause. Without overseer agents the fallback establishes no accuracy, so nothing of it is exercised and the
    pass says so: arena round 9's results audit found every c2 decision withheld for that reason alone, read as if the
    90% rule had been tested."""
    ran = [t for t in tasks if (t.get("overseer") or {}).get("ran") and not t["overseer"].get("timed_out") and not t["overseer"].get("error")]
    # an accuracy is established only by a counted verdict: a stage whose every run failed (a provider error, say) ran, but
    # established nothing, whatever cause the decision's label states
    established = [t for t in ran if t["overseer"].get("verdicts_counted")]
    by_why: dict[str, int] = {}
    for t in tasks:
        if t.get("mode") == "withheld":
            why = t.get("withheld_why") or "other"
            by_why[why] = by_why.get(why, 0) + 1
    out = {"fallback_exercised": bool(established), "decided_on_established_accuracy": len(established),
           "overseer_selected": sum(1 for t in tasks if t.get("mode") == "overseer_selected"), "withheld_by_cause": by_why,
           "overseer_stage_without_counted_verdict": [t["file"] for t in ran if not t["overseer"].get("verdicts_counted")]}
    if not established:
        out["fallback_not_exercised"] = ("no overseer agent is configured (the harness calls no model): no accuracy was established, so neither the "
                                         "overseer-selected fallback above the threshold nor the below-threshold rule was exercised" if not configured else
                                         "the overseer agents established no accuracy on any answer (their stage did not run, ran out of its budget, failed, "
                                         "or no verdict of theirs was counted), so neither the overseer-selected fallback nor the below-threshold rule was "
                                         "exercised")
    return out


def delivery_comparison(configured: dict, baseline: dict) -> dict:
    """The configured delivery pass beside the withheld baseline (the same pass without overseer agents): per task, the
    baseline's mode and the configured pass's, and the tasks whose decision the overseer agents changed."""
    base = {t["file"]: t for t in baseline.get("tasks", [])}
    rows = []
    for t in configured.get("tasks", []):
        b = base.get(t["file"]) or {}
        rows.append({"file": t["file"], "baseline_mode": b.get("mode"), "mode": t.get("mode"), "withheld_why": t.get("withheld_why"),
                     "baseline_withheld_why": b.get("withheld_why")})
    return {"tasks": rows, "changed": [r["file"] for r in rows if r["mode"] != r["baseline_mode"]],
            "by_mode": configured.get("by_mode", {}), "baseline_by_mode": baseline.get("by_mode", {})}


def _candidate_line(c: dict) -> str:
    flags = [f for f, on in (("refuted", c.get("refuted")), ("faulted", c.get("faulted") and not c.get("refuted")),
                             ("not deliverable", not c.get("deliverable", True))) if on]
    return f"{c.get('agent_id')} {c.get('accuracy_fraction')}" + (f" ({', '.join(flags)})" if flags else "")


def delivery_record(item: dict, decision, keyring, *, genuine: dict | None, rc, policy) -> dict:
    """One task's delivery decision as results.json reports it: the mode, the label, the time to decision, the
    translation and overseer times, the formal path's reasons and claims, every candidate with its accuracy and the one
    chosen, the reasons, the signed receipt's id and whether it verifies, and whether the delivery pass's receipt is the
    genuine record's (status and codes)."""
    from epinoic_overseer.delivery_policy import DeliveryPolicy, verify_delivery_receipt
    r = decision.receipt
    fb = r.fallback
    codes = sorted({f.code for f in rc.findings} | {sf.code for sf in rc.structural_findings}) if rc is not None else None
    status = rc.status.value if rc is not None else None
    same = genuine is not None and genuine.get("status") == status and genuine.get("codes") == codes
    out = {
        "file": item["_path"].name, "task_id": item["task_id"], "group": group_of(item), "agent_id": item["agent_id"], "subject": item["subject"],
        "mode": decision.mode, "delivered": decision.delivered, "label": decision.label,
        "withheld_why": _withheld_why(decision.label, getattr(DeliveryPolicy, "_WITHHELD_WHY", {})) if decision.mode == "withheld" else None,
        "time_to_decision_s": r.time_to_decision_s,
        "translation_s": r.translation_s, "overseer_s": r.overseer_s,
        "formal": {"complete": r.formal.complete, "within_budget": r.formal.within_budget, "reasons": list(r.formal.reasons),
                   "claims": [{"claim_id": c.claim_id, "outcome": c.outcome, "display_status": c.display_status, "translation_status": c.translation_status,
                               "reasons": list(c.reasons[:4])} for c in r.formal.claims],
                   "branch_checks_not_holding": [b.constraint_id for b in r.formal.branch_checks if b.satisfied is not True]},
        "candidates": [{"message_id": c.message_id, "agent_id": c.agent_id, "accuracy": c.accuracy, "accuracy_fraction": c.accuracy_fraction,
                        "above_threshold": c.above_threshold, "refuted": c.refuted, "faulted": c.faulted, "deliverable": c.deliverable,
                        "integrity_reasons": list(c.integrity_reasons), "chosen": fb is not None and c.message_id == fb.chosen_message_id,
                        "claims": {a: sum(1 for x in c.claims if x.assessment == a) for a in ("accurate", "inaccurate", "contested", "unassessed")}}
                       for c in (fb.candidates if fb is not None else [])],
        "chosen": ({"message_id": r.delivered_message_id, "agent_id": r.delivered_agent_id} if r.delivered else None),
        "overseer": ({"configured": fb.overseer.configured, "ran": fb.overseer.ran, "timed_out": fb.overseer.timed_out, "error": fb.overseer.error,
                      "instances": list(fb.overseer.instances), "runs": [dict(x) for x in fb.overseer.runs],
                      "verdicts_counted": sum(1 for v in fb.overseer.verdicts if v.counted), "verdicts": len(fb.overseer.verdicts)}
                     if fb is not None else None),
        "why_fallback": list(fb.why) if fb is not None else [], "selection": list(fb.selection) if fb is not None else [], "reasons": list(r.reasons),
        "delivery_receipt_id": r.receipt_id, "receipt_verifies": verify_delivery_receipt(r, keyring),
        "delivery_pass_status": status, "delivery_pass_codes": codes, "receipt_matches_genuine_record": same,
    }
    if not same and genuine is not None:
        out["genuine_record"] = {"status": genuine.get("status"), "codes": genuine.get("codes")}
    return out


def delivery_pass(items: list[dict], make_verify_fn, recorded_relays: dict, records: list[dict], *, overseer: dict | None = None) -> dict:
    """The delivery policy (``epinoic_overseer.delivery_policy``, ``docs/DELIVERY.md``) applied to every genuine
    answer of the round, on a hub of its own carrying a transfer auditor: each group's genuine traffic is replayed in the
    genuine pass's order (requests, peer relays, answers with the same fixtures) and, for each answer, a delivery session
    starts when the answer reaches the hub and decides: formally_checked, overseer_selected, not_checked or withheld,
    with the time to decision, the candidates and the one chosen. ``overseer`` (``{"pack": ..., "provider_factory": ...,
    "pool_config": ...}``) configures the fallback's overseer agents; without it (the command line: the harness calls no
    model) the fallback establishes no accuracy, so an answer the formal path does not complete is withheld. The pass
    changes no record of the round and no transport count: its records are ``deliveries``, a measure of its own. Where
    the overseer is not installed the pass is not run and says so (:data:`OVERSEER_NOT_INSTALLED`).

    Whether the pass exercised the overseer-selected fallback is counted from its records (``fallback_accounting``:
    ``fallback_exercised``, the decisions taken on an established accuracy, the overseer-selected ones and the withheld
    ones by cause, ``withheld_why`` on each task), and a pass that did not says why (``fallback_not_exercised``), so a
    withheld baseline is never read as a test of the threshold. ``overseer`` may name its agents (``label``: the
    ``--overseer-provider`` the command line was given); its other keys are the policy's (:data:`DELIVERY_POLICY_KEYS`)."""
    if not overseer_installed():
        return {"skipped": OVERSEER_NOT_INSTALLED, "tasks": [], "by_mode": {}, "errors": []}
    from epinoic_overseer.delivery_policy import DELIVERY_POLICY_VERSION, DeliveryConfig, DeliveryPolicy
    t_pass = time.perf_counter()
    cfg = DeliveryConfig()
    label = (overseer or {}).get("label")
    out = {"policy": DELIVERY_POLICY_VERSION, "translation_budget_s": cfg.translation_budget_s, "overseer_budget_s": cfg.overseer_budget_s,
           "min_selected_accuracy": cfg.min_selected_accuracy,
           "overseer": (f"configured ({label}, through the overseer package's runner and verdict intake)" if label else "configured") if overseer else
                       "not configured (the harness calls no model): the fallback establishes no accuracy",
           "tasks": [], "by_mode": {m: 0 for m in ("formally_checked", "overseer_selected", "not_checked", "withheld")}, "errors": []}
    genuine = {r["file"]: r for r in records if r.get("variant") == "genuine"}
    try:
        auditor = _delivery_auditor()
        hub = _DeliveryHub(signing_key=KEY, config=CFG, auditor=auditor)
        agents = {k: v for k, v in (overseer or {}).items() if k in DELIVERY_POLICY_KEYS}
        if agents.get("provider_factory") is not None and agents.get("pack") is None:  # --overseer-provider: load the exported pack here
            import tempfile

            from epinoic_overseer import export_pack, load_pack
            if (overseer or {}).get("pack_zip") is not None:
                agents["pack"] = load_pack(Path(overseer["pack_zip"]))
            else:
                with tempfile.TemporaryDirectory(prefix="arena-overseer-pack-") as tmp:
                    agents["pack"] = load_pack(export_pack(Path(tmp), zip_archive=True).zip_path)
        policy = DeliveryPolicy(config=cfg, clock=time.monotonic, **agents)
    except Exception as exc:  # a failure of the pass never ends the round
        out["errors"].append({"error": f"the delivery pass could not start: {type(exc).__name__}: {exc}"})
        return out
    channels: dict[str, object] = {}
    delivered: dict[str, object] = {}
    peer_docs: dict[str, SuppliedText] = {}
    try:
        for item in items:
            sp, task_id, group = item["_path"], item["task_id"], group_of(item)
            try:
                if group not in channels:
                    channels[group] = hub.open_task(group_plan(items, group))
                ch = channels[group]
                texts = supplied(item)
                if item.get("peer_of"):
                    recorded_doc = recorded_relays[task_id]["payload"].get("original_response") if task_id in recorded_relays else None
                    _rec, ptext, _relayed = relay_from_peer(ch, items, item, delivered, sp.name, recorded_doc)
                    if ptext is None:
                        out["tasks"].append({"file": sp.name, "task_id": task_id, "group": group, "agent_id": item["agent_id"], "subject": item["subject"],
                                             "mode": "withheld", "delivered": False, "reasons": ["the agent answered nothing: its peer report was not relayed"]})
                        out["by_mode"]["withheld"] += 1
                        continue
                    peer_docs[task_id] = ptext
                    texts = [*texts, ptext]
                key = ch.plan.task_id
                m, _req, _rq = hub.dispatch(key, item["agent_id"], item["question"], texts)
                if m is None:
                    out["errors"].append({"file": sp.name, "error": "the request was rejected in the delivery pass"})
                    continue
                ch.verify_claim_fn = make_verify_fn(sp.stem, False, _DELIVERY_VERIFY_CLAIM)
                session = policy.start(hub, key)
                session.install()
                reply, rc = hub.receive(key, m.message_id, item["response_text"], agent_id=item["agent_id"], report_id=f"rep-{task_id}-0")
                if reply is not None:
                    delivered[sp.stem] = reply
                decision = session.decide(request_message_ids=[m.message_id], receipts={rc.message_id: rc})
                rec = delivery_record(item, decision, auditor.keyring, genuine=genuine.get(sp.name), rc=rc, policy=policy)
                out["tasks"].append(rec)
                out["by_mode"][decision.mode] = out["by_mode"].get(decision.mode, 0) + 1
            except Exception as exc:  # recorded, never allowed to end the round
                out["errors"].append({"file": sp.name, "error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()[-1500:]})
    finally:
        try:
            hub.close()
        except Exception:
            pass
    out["receipts_matching_genuine_records"] = sum(1 for t in out["tasks"] if t.get("receipt_matches_genuine_record"))
    out["decided"] = sum(1 for t in out["tasks"] if "delivery_receipt_id" in t)
    out.update(fallback_accounting(out["tasks"], bool(overseer)))
    out["wall_s"] = round(time.perf_counter() - t_pass, 3)  # the pass's own wall time (a measure for the optimisation checks)
    return out


def delivery_lines(d: dict) -> list[str]:
    """summary.md's delivery section: one row per task (mode, time to decision, candidates and the one chosen)."""
    if d.get("skipped"):
        return ["## Delivery decisions", "", f"(not run: {d['skipped']})"]
    lines = ["## Delivery decisions (delivery policy " + str(d.get("policy")) + f": {d.get('translation_budget_s', 0):g} s translation budget, "
             f"overseer-selected fallback above {d.get('min_selected_accuracy', 0):g}; docs/DELIVERY.md)", "",
             "Each genuine answer is replayed on a hub of its own with the transfer auditor attached and decided by the delivery policy. "
             f"Overseer agents: {d.get('overseer')}. A separate measure: it changes no transport count. Modes: "
             + ", ".join(f"{k} {v}" for k, v in d.get("by_mode", {}).items()) + f"; receipts identical to the genuine records' (status and codes): "
             f"{d.get('receipts_matching_genuine_records', 0)} of {d.get('decided', 0)}; the pass took {d.get('wall_s', 0):g} s.", "",
             fallback_line(d), "",
             "| task | mode | time to decision (s) | translation (s) | overseer (s) | candidates (accuracy) | chosen | why |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for t in d.get("tasks", []):
        why = (t.get("why_fallback") or t.get("reasons") or [""])[0] if t.get("mode") != "formally_checked" else "formal path complete"
        why = (why[:160] + "…") if len(why) > 160 else why
        cands = "; ".join(_candidate_line(c) for c in t.get("candidates", [])) or "-"
        chosen = (t.get("chosen") or {}).get("agent_id") or "-"
        ov = "-" if t.get("overseer_s") is None else f"{t['overseer_s']:.3f}"
        tr = "-" if t.get("translation_s") is None else f"{t['translation_s']:.3f}"
        ttd = "-" if t.get("time_to_decision_s") is None else f"{t['time_to_decision_s']:.3f}"
        lines.append(f"| {t['file']} | {t['mode']} | {ttd} | {tr} | {ov} | {cands} | {chosen} | {why.replace('|', '/')} |")
    for e in d.get("errors", []):
        lines.append(f"- delivery pass error: {e.get('file', '')} {e.get('error')}")
    if not d.get("tasks"):
        lines.append("(no task)")
    return lines


def fallback_line(d: dict) -> str:
    """summary.md's statement of what the delivery pass exercised of the overseer-selected fallback (``fallback_accounting``)."""
    causes = ", ".join(f"{k} {v}" for k, v in sorted((d.get("withheld_by_cause") or {}).items())) or "none"
    empty = d.get("overseer_stage_without_counted_verdict") or []
    tail = (f" The overseer stage ran with no counted verdict (nothing established, whatever cause the label states) on: {', '.join(empty)}."
            if empty else "")
    if not d.get("fallback_exercised"):
        return (f"Overseer-selected fallback: NOT exercised in this pass: {d.get('fallback_not_exercised') or 'no accuracy was established'}. "
                f"Withheld by cause: {causes}.{tail}")
    return (f"Overseer-selected fallback: exercised: {d.get('decided_on_established_accuracy', 0)} decision(s) on an accuracy the overseer agents' "
            f"counted verdicts established; overseer-selected {d.get('overseer_selected', 0)}; withheld by cause: {causes}.{tail}")


def delivery_baseline_lines(base: dict, comparison: dict) -> list[str]:
    """summary.md's section on the withheld baseline: the same delivery pass without overseer agents, beside the
    configured pass above, with every decision the overseer agents changed."""
    if base.get("skipped"):
        return ["## Delivery decisions without overseer agents (the withheld baseline)", "", f"(not run: {base['skipped']})"]
    lines = ["## Delivery decisions without overseer agents (the withheld baseline)", "",
             "The same pass with no overseer agent: every answer whose formal path does not complete is withheld. Modes: "
             + ", ".join(f"{k} {v}" for k, v in base.get("by_mode", {}).items()) + f"; with the overseer agents: "
             + ", ".join(f"{k} {v}" for k, v in comparison.get("by_mode", {}).items()) + ".", ""]
    changed = set(comparison.get("changed", []))
    lines += [f"- {r['file']}: {r['baseline_mode']}" + (f" ({r['baseline_withheld_why']})" if r.get("baseline_withheld_why") else "") + f" -> {r['mode']}"
              + (f" ({r['withheld_why']})" if r.get("withheld_why") else "") for r in comparison.get("tasks", []) if r["file"] in changed]
    if not changed:
        lines.append("(the overseer agents changed no decision)")
    lines += [f"- baseline pass error: {e.get('file', '')} {e.get('error')}" for e in base.get("errors", [])]
    return lines


# ============================================================================================ specialist feedback (design section 53)
#: Where ``revision_feedback.py`` writes the infrastructure's feedback on each genuine answer (``<round>/feedback/<task>.json``)
#: and where the round's pipeline records each specialist's revision (``<round>/revisions/<task>.json``).
FEEDBACK_DIR = "feedback"
REVISIONS_DIR = "revisions"
#: The keys of a feedback file. ``rendered`` is the one part the specialist reads (its next turn, after its own answer);
#: the rest is the router's record: whether a revision request was issued and, if not, why; the signed block, its digest,
#: the flaws (code, severity, class, basis, rule, claim ids, fault signature) and the number of advisory items.
FEEDBACK_FILE_KEYS = ("task_id", "agent_id", "answer_status", "issued", "reason", "round", "max_rounds", "rendered", "rendered_sha256", "block", "flaws",
                      "advisory", "refusal")
#: The keys a revision file must carry; the pipeline records the specialist's call beside them (model, effort, kb_version,
#: bundle_sha256, started_at, finished_at, elapsed_s, input_tokens, output_tokens), which the harness reports as given.
REVISION_FILE_REQUIRED = ("task_id", "agent_id", "feedback_sha256", "response_text")
#: The fields of a feedback file a re-issued request must reproduce exactly (recorded_feedback_checks).
FEEDBACK_COMPARED = ("issued", "reason", "round", "max_rounds", "rendered_sha256", "flaws", "keep")
#: The shadow's codes on a transfer it does not reproduce (OVS-RCPT-004 a finding missing, 005 a finding the shadow does not
#: raise, 008 another status or other structured results).
SHADOW_CODES = ("OVS-RCPT-004", "OVS-RCPT-005", "OVS-RCPT-008")
#: The flag of a revision file that does not record the digest of the message its specialist read (``feedback_sha256``):
#: without it no replay can show that the specialist read the feedback as issued, so gate ``feedback_as_read`` fails.
UNRECORDED_READ_FLAG = ("the revision file does not record the feedback its specialist read (no feedback_sha256): the replay cannot show "
                        "that the specialist read the feedback as issued")


def _is_budget(value) -> bool:
    from epinoic_logic.channel.contracts import HARD_MAX_REVISION_ROUNDS
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= HARD_MAX_REVISION_ROUNDS


def recorded_feedback_budget(doc) -> int | None:
    """The revision budget a recorded feedback file (``feedback/<task>.json``) was issued under: the signed block's
    ``max_rounds`` when the file holds a block (what the specialist read: 'Revision request 1 of 1'), else the file's own
    ``max_rounds`` (``feedback_document`` records the plan's budget for an answer that got no request too, such as
    ``no_actionable_flaw``). None when the file records neither, or a value that is no budget (not an integer from 1 to
    the hard maximum; a bool is no integer here)."""
    if not isinstance(doc, dict):
        return None
    block = doc.get("block")
    for value in ((block.get("max_rounds") if isinstance(block, dict) else None), doc.get("max_rounds")):
        if _is_budget(value):
            return value
    return None


def replay_budgets(items: list[dict], recorded: dict) -> tuple[list[dict], dict[str, dict]]:
    """The revision pass's items, each re-issued under the budget its recorded feedback was issued under (arena round 9,
    c2: the feedback was issued under one revision round, 'Revision request 1 of 1', while the round's tasks.json recorded
    no ``revision_rounds``, so the replay re-issued every request under the default budget and gate ``feedback_as_read``
    failed on configuration for all 15 revisions, not on custody). Per task with a recorded budget
    (``recorded_feedback_budget``): the round's own setting (the specialist file's or tasks.json's ``revision_rounds``) when
    it agrees (source ``round``), else the recorded budget (source ``feedback``), naming the round's other setting
    (``round_budget``) when there is one. Returns copies of the items (the caller's are never changed) and ``{task id:
    {"max_rounds", "source", "round_budget"?}}``. A group's plan carries one budget (``group_plan``: the smallest its
    members set), so a group whose recorded files disagree reproduces at most one of them, and the comparison names the
    others."""
    out_items: list[dict] = []
    budgets: dict[str, dict] = {}
    for it in items:
        it = dict(it)
        budget = recorded_feedback_budget(recorded.get(it["task_id"]))
        if budget is not None:
            own = it.get("revision_rounds")
            if own == budget and _is_budget(own):
                budgets[it["task_id"]] = {"max_rounds": budget, "source": "round"}
            else:
                budgets[it["task_id"]] = {"max_rounds": budget, "source": "feedback"} | ({"round_budget": own} if own is not None else {})
                it["revision_rounds"] = budget
        out_items.append(it)
    return out_items, budgets


class UnreadableFile(str):
    """Why a recorded feedback or revision file could not be read as JSON (``_json_file``): kept in its file's place, so
    the revision pass names it as a difference or an error instead of raising."""


def _json_file(p: Path):
    """``(value, None)`` for a JSON file, ``(None, why)`` for one that cannot be read as JSON (never raised: a round's
    feedback and revision files are recorded material, and one bad file never stops the pass)."""
    try:
        return json.loads(p.read_text(encoding="utf-8")), None
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return None, f"not JSON ({type(exc).__name__})"


def record_revision_budget(round_dir: Path, items: list[dict], revision_rounds: int, task_ids=None) -> dict:
    """Record in the round the revision budget its feedback is issued under (arena round 9, c2: the feedback was issued
    under one revision round while the round recorded none, so no replay could re-issue it as the specialists read it).
    Every covered task (``task_ids``, else every task of the round) of ``<round>/tasks.json`` gets ``revision_rounds``,
    the round's setting ``load_items`` reads; a task that already records another budget (in tasks.json or in its
    specialist file) is refused with ValueError, before anything is written, never overwritten. The items of the covered
    groups carry the budget too, so the replay that issues the feedback plans with it. A round without tasks.json records
    the budget in its feedback files only (each one's ``max_rounds`` and signed block), which the revision pass reads
    (``recorded_feedback_budget``). Returns ``{"revision_rounds", "recorded_in", "tasks"}``."""
    if not _is_budget(revision_rounds):
        raise ValueError(f"revision_rounds must be an integer from 1 to the hard maximum, not {revision_rounds!r} (0 disables feedback: issue none)")
    covered = set(task_ids) if task_ids else {it["task_id"] for it in items}
    tasks_file = round_dir / "tasks.json"
    tasks = json.loads(tasks_file.read_text(encoding="utf-8")) if tasks_file.exists() else None
    entries = [t for t in (tasks if isinstance(tasks, list) else []) if isinstance(t, dict) and t.get("task_id") in covered]
    # every conflict is refused before anything is written or changed
    for where, task_id, own in ([("its specialist file or tasks.json", it["task_id"], it.get("revision_rounds")) for it in items if it["task_id"] in covered]
                                + [("tasks.json", t["task_id"], t.get("revision_rounds")) for t in entries]):
        if own is not None and own != revision_rounds:
            raise ValueError(f"task {task_id} records revision_rounds {own!r} in {where}; refusing to issue its feedback under {revision_rounds}")
    groups = {group_of(it) for it in items if it["task_id"] in covered}
    for it in items:
        if group_of(it) in groups and it.get("revision_rounds") is None:
            it["revision_rounds"] = revision_rounds
    changed = False
    for t in entries:
        if t.get("revision_rounds") is None:
            t["revision_rounds"] = revision_rounds
            changed = True
    if changed:
        tasks_file.write_text(json.dumps(tasks, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    recorded = sorted(t["task_id"] for t in entries)
    return {"revision_rounds": revision_rounds, "recorded_in": "tasks.json" if recorded else None, "tasks": recorded}


def _feedback_replay(items: list[dict], recorded_relays: dict | None = None, *, auditor=None, task_ids=None):
    """Each group's genuine traffic replayed on a hub of its own carrying a transfer auditor (the delivery pass's unless
    ``auditor`` is given), in the genuine pass's order: the requests, the peer relays (the recorded relayed document when
    there is one) and the answers, with no translator fixture (no claim outcome is ever fed back, so the flaws do not
    depend on one); then, for every genuine specialist answer (standalone and peer-dependent, never a synthesis;
    ``task_ids`` limits them), the infrastructure's revision request (``RouterHub.request_revision``: the flaws come from
    the answer's receipt and a signed task audit, never from an agent). Returns ``(hub, entries)``: per task id its item,
    hub key, request, answer (None when not delivered), receipt and ``RevisionIssue``, or ``error``. The caller closes
    the hub."""
    hub = _DeliveryHub(signing_key=KEY, config=CFG, auditor=auditor if auditor is not None else _delivery_auditor())
    channels: dict[str, object] = {}
    delivered: dict[str, object] = {}
    entries: dict[str, dict] = {}
    recorded_relays = recorded_relays or {}
    for item in items:
        sp, task_id, group = item["_path"], item["task_id"], group_of(item)
        entry = entries[task_id] = {"item": item, "key": group}
        try:
            if group not in channels:
                channels[group] = hub.open_task(group_plan(items, group))
            texts = supplied(item)
            if item.get("peer_of"):
                recorded_doc = recorded_relays[task_id]["payload"].get("original_response") if task_id in recorded_relays else None
                _rec, ptext, _relayed = relay_from_peer(channels[group], items, item, delivered, sp.name, recorded_doc)
                if ptext is None:
                    entry["error"] = "its peer report was not relayed"
                    continue
                texts = [*texts, ptext]
            m, _req, rq = hub.dispatch(group, item["agent_id"], item["question"], texts)
            if m is None:
                entry["error"] = f"its request was {rq.status.value}"
                continue
            reply, rc = hub.receive(group, m.message_id, item["response_text"], agent_id=item["agent_id"], report_id=f"rep-{task_id}-0")
            entry.update(request=m, answer=reply, receipt=rc, receipt_dump=rc.model_dump(mode="json"))
            if reply is not None:
                delivered[sp.stem] = reply
        except Exception as exc:  # recorded, never allowed to end the round
            entry["error"] = f"{type(exc).__name__}: {exc}"
    for task_id, entry in entries.items():
        if entry.get("error") or (task_ids is not None and task_id not in task_ids):
            continue
        try:
            t0 = time.perf_counter()
            entry["issue"] = hub.request_revision(entry["key"], entry["receipt"].message_id)
            entry["issue_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
    return hub, entries


def feedback_document(entry: dict) -> dict:
    """The content of ``<round>/feedback/<task>.json`` (FEEDBACK_FILE_KEYS, nothing else) for one replayed answer."""
    item, issue, rc = entry["item"], entry.get("issue"), entry.get("receipt")
    doc = {k: None for k in FEEDBACK_FILE_KEYS}
    doc.update(task_id=item["task_id"], agent_id=item["agent_id"], answer_status=rc.status.value if rc is not None else None, issued=False,
               reason="not_replayed" if issue is None else issue.reason, flaws=[], advisory=0)
    if issue is None:
        doc["refusal"] = entry.get("error")
        return doc
    doc.update(round=issue.round or None, max_rounds=issue.max_rounds or None)
    if issue.receipt is not None and not issue.allowed:
        doc["refusal"] = "; ".join(f"{f.code}: {f.message[:400]}" for f in issue.receipt.findings if f.severity == "error") or None
    if issue.escalation is not None:
        doc["refusal"] = f"escalated: {issue.escalation.reason}"
    if issue.allowed and issue.revision is not None:
        block = issue.revision
        doc.update(issued=True, rendered=issue.rendered, rendered_sha256=block.rendered_sha256, block=block.model_dump(mode="json", exclude_none=True),
                   flaws=[{"flaw_id": f.flaw_id, "code": f.code, "severity": f.severity, "flaw_class": f.flaw_class, "basis": f.basis, "rule": f.rule,
                           "claim_ids": [c.claim_id for c in f.claims], "signature": f.signature} for f in block.flaws],
                   advisory=sum(1 for f in block.flaws if f.basis == "advisory"))
    return doc


def _keep_of(doc: dict | None) -> list | None:
    return None if doc is None or not doc.get("block") else doc["block"].get("must_not_change")


def feedback_differences(recorded: dict, current: dict | None) -> list[str]:
    """The fields of FEEDBACK_COMPARED in which the re-issued request differs from the recorded feedback file (empty when the
    specialist read what this code issues): a difference means the feedback differs from what the specialist read."""
    if not isinstance(recorded, dict):
        return ["the recorded feedback file is not a JSON object"]
    if current is None:
        return ["the answer was not replayed"]
    out = []
    for k in FEEDBACK_COMPARED:
        a, b = (_keep_of(recorded), _keep_of(current)) if k == "keep" else (recorded.get(k), current.get(k))
        if a != b:
            out.append(k)
    return out


def revision_feedback(round_dir: Path, task_ids=None, *, revision_rounds: int | None = None) -> dict:
    """Build, through the audited hub, the infrastructure's feedback on every genuine answer of the round (or on
    ``task_ids``) and write ``<round>/feedback/<task_id>.json`` (``feedback_document``). Returns the files and the count by
    reason. Nothing is sent to a specialist: the pipeline sends ``rendered`` as the specialist's next turn.

    ``revision_rounds`` issues the feedback under that budget and records it in the round first
    (``record_revision_budget``: tasks.json's ``revision_rounds`` of every covered task; a task that records another
    budget is refused before anything is written), so a replay re-issues the requests exactly as the specialists read
    them. Without it the round's own setting applies (tasks.json or the specialist file), else the channel's default.
    Either way each feedback file records the budget it was issued under (``max_rounds``, and the signed block's)."""
    items = load_items(round_dir / "specialists")
    wanted = set(task_ids) if task_ids else None
    budget = record_revision_budget(round_dir, items, revision_rounds, wanted) if revision_rounds is not None else None
    hub, entries = _feedback_replay(items, load_recorded_relays(round_dir, items), task_ids=wanted)
    out = {"files": [], "by_reason": {}, "issued": 0, "budget": budget}
    try:
        (round_dir / FEEDBACK_DIR).mkdir(exist_ok=True)
        for task_id, entry in entries.items():
            if wanted is not None and task_id not in wanted:
                continue
            doc = feedback_document(entry)
            path = round_dir / FEEDBACK_DIR / f"{task_id}.json"
            path.write_text(json.dumps(doc, indent=2, ensure_ascii=False, default=str))
            out["files"].append(str(path))
            out["by_reason"][doc["reason"]] = out["by_reason"].get(doc["reason"], 0) + 1
            out["issued"] += 1 if doc["issued"] else 0
            out.setdefault("tasks", []).append({k: doc[k] for k in ("task_id", "agent_id", "issued", "reason")} | {"codes": [f["code"] for f in doc["flaws"]]})
    finally:
        hub.close()
    return out


def _consolidation_state(hub, key: str, mids: list[str]) -> dict:
    try:
        resp = hub.consolidate(key, request_message_ids=mids)
        return {"status": resp.status, "deliverable_message_id": resp.deliverable_message_id, "excluded": sorted(resp.excluded_message_ids())}
    except Exception as exc:  # recorded, never allowed to end the pass
        return {"error": f"{type(exc).__name__}: {exc}"}


def revision_pass(round_dir: Path, items: list[dict], recorded_relays: dict) -> dict:
    """The specialist revisions of the round (design section 53), a measure of its own: only when the round has a
    ``feedback/`` directory. Each group's genuine traffic is replayed on an audited hub and each request re-issued
    (``recorded_feedback_checks``: the flaws, the keep list and the rendered digest against what was recorded; a difference
    means the feedback differs from what the specialist read); each recorded revision (``revisions/<task>.json``) is
    delivered in reply to it under the report id ``rep-<task>-rev1``, the task audit runs with the shadow, and each
    revision's outcome (fixed, removed, evaded, persisted, not re-checked; introduced flaws, preservation findings, claims
    lost; the next step) and its consolidation before and after are recorded with the times. The pass adds no record to
    the round and moves no transport count: the headline rate excludes it. Where the overseer is not installed the pass
    is not run and says so (:data:`OVERSEER_NOT_INSTALLED`).

    Each request is re-issued under the budget its recorded feedback was issued under (``replay_budgets``; each check
    names its ``max_rounds`` and where the budget came from), so gate ``feedback_as_read`` decides custody, not the
    round's configuration (arena round 9, c2). A revision file that does not record the digest of the message its
    specialist read is flagged (:data:`UNRECORDED_READ_FLAG`) and fails that gate. A file in ``feedback/`` or
    ``revisions/`` whose name is no task of the round and that carries no ``task_id`` (an exercise's own summary, say) is
    no feedback or revision file: it is listed under ``ignored_files``, never compared; a feedback or revision file that is
    not JSON is a named difference or error, never an exception."""
    fb_dir, rev_dir = round_dir / FEEDBACK_DIR, round_dir / REVISIONS_DIR
    if not fb_dir.is_dir():
        return {"skipped": "the round has no feedback/ directory (scripts/arena/revision_feedback.py was not run)", "tasks": [], "checks": [], "errors": []}
    if not overseer_installed():
        return {"skipped": OVERSEER_NOT_INSTALLED, "tasks": [], "checks": [], "errors": []}
    t_pass = time.perf_counter()
    task_names = {it["task_id"] for it in items}
    ignored: list[dict] = []

    def read_dir(d: Path, kind: str) -> dict:
        found: dict = {}
        for p in sorted(d.glob("*.json")) if d.is_dir() else []:
            value, why = _json_file(p)
            if p.stem not in task_names and not (isinstance(value, dict) and "task_id" in value):
                ignored.append({"file": f"{d.name}/{p.name}", "why": f"no {kind} file: its name is no task of the round and it carries no task_id"
                                                                       + (f" ({why})" if why else "")})
                continue
            found[p.stem] = value if why is None else UnreadableFile(why)  # an unreadable file is kept as its reason, never raised on
        return found
    recorded = read_dir(fb_dir, "feedback")
    revisions = read_dir(rev_dir, "revision")
    out: dict = {"tasks": [], "checks": [], "errors": [], "answers_checked": 0, "feedback_issued": 0, "negative_controls": 0, "ignored_files": ignored}
    replay_items, budgets = replay_budgets(items, {k: v for k, v in recorded.items() if isinstance(v, dict)})
    out["budgets"] = budgets
    try:
        hub, entries = _feedback_replay(replay_items, recorded_relays)
    except Exception as exc:
        out["errors"].append({"error": f"the revision pass could not start: {type(exc).__name__}: {exc}"})
        return out
    try:
        for task_id, entry in entries.items():
            if entry.get("receipt") is not None:
                out["answers_checked"] += 1
            issue = entry.get("issue")
            if issue is not None and issue.allowed:
                out["feedback_issued"] += 1
            elif issue is not None and issue.reason == "no_actionable_flaw":
                out["negative_controls"] += 1
        for task_id, rec in recorded.items():
            entry = entries.get(task_id)
            if isinstance(rec, UnreadableFile):
                diff = [f"the recorded feedback file is {rec}"]
            else:
                diff = feedback_differences(rec, feedback_document(entry) if entry is not None else None)
            check = {"task_id": task_id, "identical": not diff, "differences": diff}
            if task_id in budgets:
                check["budget"] = dict(budgets[task_id])
            out["checks"].append(check)
        groups: dict[str, list[str]] = {}
        for task_id, rev in revisions.items():
            entry = entries.get(task_id)
            issue = (entry or {}).get("issue")
            rec = {"task_id": task_id, "agent_id": (entry or {}).get("item", {}).get("agent_id"), "delivered": False}
            if not isinstance(rev, dict):
                rec["error"] = f"the revision file is {rev}" if isinstance(rev, UnreadableFile) else "the revision file is not a JSON object"
                rec["flag"] = UNRECORDED_READ_FLAG
                out["tasks"].append(rec)
                continue
            missing = [k for k in REVISION_FILE_REQUIRED if k not in rev]
            if missing or issue is None or not issue.allowed:
                rec["error"] = (f"the revision file lacks {missing}" if missing else
                                f"no revision request was issued for this answer ({issue.reason if issue is not None else (entry or {}).get('error')}): "
                                "a revision of a flawless answer, or of one whose chain ended, is never delivered")
                if "feedback_sha256" in missing:
                    rec["flag"] = UNRECORDED_READ_FLAG
                out["tasks"].append(rec)
                continue
            rec["feedback_read"] = rev["feedback_sha256"] == issue.revision.rendered_sha256
            held = recorded.get(task_id)
            if not rec["feedback_read"] or (task_id in recorded and (not isinstance(held, dict) or held.get("rendered_sha256") != issue.revision.rendered_sha256)):
                rec["flag"] = "feedback differs from what the specialist read"
            key = entry["key"]
            rec["consolidation_before"] = _consolidation_state(hub, key, [entry["request"].message_id])
            t0 = time.perf_counter()
            r2, rc2 = hub.receive(key, issue.message.message_id, rev["response_text"], agent_id=entry["item"]["agent_id"], report_id=f"rep-{task_id}-rev1")
            rec.update(delivered=r2 is not None, receive_ms=round((time.perf_counter() - t0) * 1000, 1), revision_status=rc2.status.value,
                       revision_codes=sorted({f.code for f in rc2.findings} | {sf.code for sf in rc2.structural_findings}),
                       flaws_before=[{k: f[k] for k in ("code", "severity", "flaw_class", "basis")} for f in feedback_document(entry)["flaws"]],
                       issue_ms=entry.get("issue_ms"), specialist={k: rev.get(k) for k in ("elapsed_s", "input_tokens", "output_tokens", "model", "effort",
                                                                                          "kb_version", "bundle_sha256")})
            entry.update(revision_receipt=rc2, record=rec)
            groups.setdefault(key, []).append(task_id)
            out["tasks"].append(rec)
        for key, task_ids in groups.items():
            t0 = time.perf_counter()
            audit = hub.audit(key, shadow=True)
            audit_ms = round((time.perf_counter() - t0) * 1000, 1)
            for task_id in task_ids:
                entry = entries[task_id]
                rec, issue, rc2 = entry["record"], entry["issue"], entry["revision_receipt"]
                mids = {issue.message.message_id, rc2.message_id}
                rec["audit_ms"] = audit_ms
                rec["shadow_codes"] = sorted({f.code for f in audit.report.findings if f.code in SHADOW_CODES and mids & set(f.message_ids)})
                rec["feedback_audit_codes"] = sorted({f.code for f in audit.report.findings if f.code == "OVS-FB-001" and mids & set(f.message_ids)})
                held = next((r for r in hub.channels[key].receipts if r.message_id == entry["receipt"].message_id), None)
                rec["original_receipt_unchanged"] = held is not None and held.model_dump(mode="json") == entry["receipt_dump"]
                t0 = time.perf_counter()
                outcome = hub.revision_outcome(key, rc2.message_id)
                rec["outcome_ms"] = round((time.perf_counter() - t0) * 1000, 1)
                rec.update(buckets=[{"code": f.code, "severity": f.severity, "basis": f.basis, "bucket": f.bucket, "removal_allowed": f.removal_allowed}
                                    for f in outcome.flaws],
                           introduced=[i.code for i in outcome.introduced], preservation=list(outcome.preservation), claims_lost=list(outcome.claims_lost),
                           repeats=list(outcome.repeat_signatures), next=outcome.next, escalation_reason=outcome.escalation_reason)
                rec["consolidation_after"] = _consolidation_state(hub, key, [entry["request"].message_id, issue.message.message_id])
                persisting = [b for b in rec["buckets"] if b["bucket"] == "persisted" and b["severity"] == "error"]
                after = rec["consolidation_after"]
                rec["persisting_error_withheld"] = not persisting or (rc2.message_id in after.get("excluded", []) and outcome.next == "escalated")
    except Exception as exc:  # recorded, never allowed to end the round
        out["errors"].append({"error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()[-1500:]})
    finally:
        try:
            hub.close()
        except Exception:
            pass
    out.update(revision_summary(out))
    out["wall_s"] = round(time.perf_counter() - t_pass, 3)
    return out


def revision_summary(d: dict) -> dict:
    """The round summary of its revisions: counts, the fix rate (fixed plus removed where allowed, over the flaws fed back
    less those not re-checked), the specialist's median and p90 time, and the gates."""
    tasks = [t for t in d.get("tasks", []) if t.get("delivered") or "buckets" in t]
    flaws = [b for t in tasks for b in t.get("buckets", []) if b["basis"] != "advisory"]
    n = {k: sum(1 for b in flaws if b["bucket"] == k) for k in ("fixed", "removed", "evaded", "persisted", "not_rechecked")}
    allowed = sum(1 for b in flaws if b["bucket"] == "removed" and b.get("removal_allowed"))
    base = len(flaws) - n["not_rechecked"]
    times = [float(t["specialist"]["elapsed_s"]) for t in tasks if (t.get("specialist") or {}).get("elapsed_s") is not None]
    gates = {"feedback_as_read": all(c["identical"] for c in d.get("checks", [])) and not any(t.get("flag") for t in d.get("tasks", [])),
             "no_feedback_without_request": not any("no revision request was issued" in (t.get("error") or "") for t in d.get("tasks", [])),
             "feedback_verifies": not any(t.get("feedback_audit_codes") for t in tasks),
             "shadow_agrees_on_revision_transfers": not any(t.get("shadow_codes") for t in tasks),
             "original_receipts_unchanged": all(t.get("original_receipt_unchanged", True) for t in tasks),
             "persisting_errors_withheld_and_escalated": all(t.get("persisting_error_withheld", True) for t in tasks)}
    return {"answers_revised": sum(1 for t in tasks if t.get("delivered")), "flaws_fed_back": len(flaws), "buckets": n, "removed_allowed": allowed,
            "fix_rate": ((n["fixed"] + allowed) / base) if base else None, "introduced": sum(len(t.get("introduced", [])) for t in tasks),
            "preservation_findings": sum(len(t.get("preservation", [])) for t in tasks), "claims_lost": sum(len(t.get("claims_lost", [])) for t in tasks),
            "escalated": sum(1 for t in tasks if t.get("next") == "escalated"),
            "specialist_time_s": {"median": statistics.median(times), "p90": _percentile(times, 0.9)} if times else None, "gates": gates}


def revision_lines(d: dict) -> list[str]:
    """summary.md's section on the specialist revisions: kept apart from the transport, fidelity and coverage measures
    and from the functional rate (the headline excludes it)."""
    if d.get("skipped"):
        return ["## Specialist revisions", "", f"(not run: {d['skipped']})"]
    b = d.get("buckets") or {}
    rate = "-" if d.get("fix_rate") is None else f"{d['fix_rate']:.1%}"
    st = d.get("specialist_time_s") or {}
    lines = ["## Specialist revisions (design section 53: a separate measure; the headline rate excludes it)", "",
             f"Answers checked {d.get('answers_checked', 0)}, feedback issued {d.get('feedback_issued', 0)}, answers revised {d.get('answers_revised', 0)}; "
             f"negative controls (no actionable flaw, no feedback) {d.get('negative_controls', 0)}. Flaws fed back {d.get('flaws_fed_back', 0)}: fixed {b.get('fixed', 0)}, "
             f"removed {b.get('removed', 0)} ({d.get('removed_allowed', 0)} allowed), evaded {b.get('evaded', 0)}, persisted {b.get('persisted', 0)}, "
             f"not re-checked {b.get('not_rechecked', 0)}; fix rate {rate}. Introduced {d.get('introduced', 0)}, preservation findings (INT-REV-002) "
             f"{d.get('preservation_findings', 0)}, claims lost {d.get('claims_lost', 0)}, escalated {d.get('escalated', 0)}."
             + (f" Specialist time: median {st['median']:g} s, p90 {st['p90']:g} s." if st else ""), "",
             "Gates: " + ", ".join(f"{k} {'PASS' if v else 'FAIL'}" for k, v in (d.get("gates") or {}).items()), "",
             "| task | revision | flaws (bucket) | introduced | INT-REV-002 | next | flag |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for t in d.get("tasks", []):
        if "error" in t and not t.get("delivered"):
            lines.append(f"| {t['task_id']} | not delivered | - | - | - | - | {t['error'][:160]}" + (f"; {t['flag']}" if t.get("flag") else "") + " |")
            continue
        fl = "; ".join(f"{x['code']} {x['bucket']}" for x in t.get("buckets", [])) or "-"
        lines.append(f"| {t['task_id']} | {t.get('revision_status')} | {fl} | {', '.join(t.get('introduced', [])) or '-'} | {len(t.get('preservation', []))} | "
                     f"{t.get('next', '-')} | {t.get('flag', '')} |")
    diffs = [c for c in d.get("checks", []) if not c["identical"]]
    lines += [f"- feedback differs from what the specialist read: {c['task_id']} ({', '.join(c['differences'])})" for c in diffs]
    lines += [budget_line(d.get("budgets") or {})] if d.get("budgets") else []
    lines += [f"- not a feedback or revision file, so not compared: {x['file']} ({x['why']})" for x in d.get("ignored_files", [])]
    lines += [f"- revision pass error: {e.get('error')}" for e in d.get("errors", [])]
    return lines


def budget_line(budgets: dict[str, dict]) -> str:
    """summary.md's line on the budgets the requests were re-issued under (``replay_budgets``): how many came from the
    round's own setting and how many from the recorded feedback files, naming each task whose round records another."""
    by_source: dict[str, list[str]] = {}
    for task_id, b in sorted(budgets.items()):
        by_source.setdefault(b["source"], []).append(f"{task_id} {b['max_rounds']}" + (f" (the round records {b['round_budget']})" if "round_budget" in b else ""))
    parts = []
    if by_source.get("round"):
        parts.append(f"{len(by_source['round'])} under the budget the round records (tasks.json or the specialist file), equal to the recorded feedback's")
    if by_source.get("feedback"):
        parts.append(f"{len(by_source['feedback'])} under the budget recorded in its feedback file, which the round does not record as its own: "
                     + ", ".join(by_source["feedback"]))
    return "- revision budgets the requests were re-issued under: " + "; ".join(parts)



def run_round(round_dir: Path, *, delivery_overseer: dict | None = None, task_record: bool = True, delivery_baseline: bool = False,
              without_overseer: bool = False) -> dict:
    """Run one recorded round (module docstring). ``delivery_overseer`` configures the delivery pass's overseer agents
    (``delivery_pass``); the command line passes none unless ``--overseer-provider`` names a provider factory.
    ``delivery_baseline`` (with ``delivery_overseer``; the command line sets it with ``--overseer-provider``) also runs the
    same pass without overseer agents and reports the configured pass's decisions beside that withheld baseline
    (``deliveries_baseline``, ``delivery_comparison``). ``task_record`` (default True, as production): the claim verifier
    receives the task record of the request each report answers and hands it to the translator; False replays with the
    two-argument verifier of the replays before round 8's clearance (``--without-task-record``), for comparison only."""
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
    baseline_ids: dict[str, list[str]] = {}  # file stem -> the claim ids the genuine reply was delivered under
    peer_docs: dict[str, SuppliedText] = {}
    last_in_group: dict[str, str] = {}
    # file stem -> {claim_id: sha256 of the claim text each fixture was produced for}: carried by the translations file
    # or captured from the genuine transmission, and handed to the fixture provider for every later variant
    fixture_digests: dict[str, dict[str, str]] = {stem: dict(tr.get("claim_text_sha256") or {}) for stem, tr in translations.items()}
    for it in items:
        last_in_group[group_of(it)] = it["task_id"]
    # file stem -> the tag the hub qualifies that specialist's STEM claim ids with (None for a parser that never does so on
    # another agent's account): a recorded translation keyed by either form of such an id serves the claim
    qualification_tags: dict[str, str | None] = {it["_path"].stem: qualification_tag(it) for it in items}
    agents_by_stem = {it["_path"].stem: it["agent_id"] for it in items}

    def make_verify_fn(stem: str, capture: bool, verify=None):
        """Translator agent output -> fixture provider; verify eligible claims of the task ``stem`` through the real
        pipeline. With ``capture`` (the genuine pass) each fixture is bound to the claim text it is first served for.
        ``verify`` replaces the module's ``verify_claim`` (the delivery pass passes the one bound at import).

        The verifier declares a ``task`` parameter, as production's does (``integration.runtime.live_verifier``): the
        channel then calls it ``fn(claim, report, task=<TaskRecord>)`` with the task record of the request the report
        answers (``channel.bus._accepts_task``; the delivery policy's deadline verifier passes it on), and the translator
        validates task-authority premises against the router's question as well as the supplied texts. With
        ``task_record`` False (``--without-task-record``) the record is not passed on, as in the replays before round 8's
        clearance. Round 8's translation-fidelity lens: the two-argument verifier checked a task_setting or
        arithmetic_fact premise against the supplied texts only, never against the question, so seven outcomes of the
        round were not the ones production computes for the same translations (ps-t14's unverified dependency 'cr-obs';
        E112 on a task figure no check had verified)."""
        tr = translations.get(stem)
        if not tr:
            return None
        digests = fixture_digests.setdefault(stem, {})
        provider = FixtureTranslationProvider({cid: json.dumps(obj) if not isinstance(obj, str) else obj for cid, obj in tr["claims"].items()}, claim_text_sha256=digests)

        def verify_fn(claim, report, task=None, *, _t=Translator(provider), _ids=frozenset(tr["claims"]), _capture=digests if capture else None,
                      _tag=qualification_tags.get(stem), _agent=agents_by_stem.get(stem)):
            # the recorded translation of this claim: under its own id, or, for this specialist's own report, under the other
            # form of its STEM id (the hub qualifies a report's ids after another agent's report holding them, which a
            # mutation's own hub task holds only when it is the peer's), so the listing's id and the delivered id never part
            # a claim from its translation
            key = fixture_key(claim.claim_id, _ids, _tag if report.agent_id == _agent else None)
            if key is None:
                # The replay serves recorded translations only: a claim with no recorded fixture is outside what the replay
                # checks (CLAIM_OUT_OF_SCOPE: the channel names nothing; fixture coverage reports the gap), in the round's own
                # passes and in the delivery pass alike, so the delivery pass's receipts stay the genuine records'. The
                # delivery policy's deadline verifier still records the claim as having no outcome, so the formal path reads
                # it NOT_ATTEMPTED (never checked), as in production.
                return CLAIM_OUT_OF_SCOPE
            if _capture is not None and key not in _capture:
                # the fixture was produced for the genuine text: bind it to that claim text (computed here, at verify
                # time, from the parsed report) so a re-stated claim under the same id, in either form, is refused later
                _capture[key] = sha256_text(claim.claim_text)
            translator = _t
            if key != claim.claim_id:
                # served explicitly under the delivered id: the same recorded translation, its problem naming the claim
                # (fixture_for_claim), bound to the claim text by the recorded or captured digest of its recorded id
                translator = Translator(FixtureTranslationProvider({claim.claim_id: fixture_for_claim(tr["claims"][key], key, claim.claim_id)},
                                                                   claim_text_sha256={claim.claim_id: digests[key]} if key in digests else None))
            # the task record goes on when there is one, the replay passes it and the claim verifier declares it (the
            # channel's own rule, accepts_task): a verifier that replaces verify_claim without a task parameter is called
            # exactly as before, and its outcomes then say no task record was given (task_record_given)
            verifier = verify or verify_claim
            with_task = {"task": task} if (task is not None and task_record and accepts_task(verifier)) else {}
            return verifier(claim, report, translator, config=CFG, signing_key=KEY, **with_task)
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
        variants = [(k, t, quotation_expectation(k, e, own_texts=bool(supplied(item)), any_text=bool(texts),
                                                 request_words=k == "altered_quotation" and not texts and alters_request_words(item["response_text"], item["question"], quote_texts)))
                    for k, t, e in variants] if answered else []
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
                    checks = [{"relayed_file": rel["file"], "peer_of": task_id, "dependent_task_id": dep, **payload_differences(rel["payload"], reply.payload if reply is not None else None),
                               "router_fields_exposed": list(rel["router_fields_exposed"])}
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
                    baseline_ids[sp.stem] = [c["claim_id"] for c in (reply.payload["claims"] if reply else [])]
                else:
                    # A fault counts as named only by a finding of the expected code that names an injected claim or
                    # quotes the injected words, and that the genuine record does not already carry, read in the id form
                    # of this delivery (a mutation's own hub task delivers a STEM report unqualified: baseline_in_form).
                    inj = injection(item["response_text"], kind, quote_texts, item.get("question", ""))
                    injected = injected_claim_ids(reply.payload["claims"] if reply else [], inj.markers)
                    expected_codes = SELF_REPORT_CODES if kind == "self_certification" else tuple(c for c in expected.split("|") if c != "NONE")
                    genuine_found = baseline_in_form(baseline.get(sp.stem, []), baseline_ids.get(sp.stem, []),
                                                     [c["claim_id"] for c in (reply.payload["claims"] if reply else [])], qualification_tags.get(sp.stem))
                    named = findings_naming_injection(found, expected_codes, inj, injected, genuine_found, task_id)
                    unexplained, absent = diff_against_baseline(found, genuine_found, inj, injected, task_id, baseline_constraints.get(sp.stem))
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
                # the recorded translations this delivery's claims carry under the other form of their STEM id, named on
                # every record that served one (the genuine report qualified after another agent's, a mutation not)
                qtag = qualification_tags.get(sp.stem)
                delivered_ids = [c["claim_id"] for c in (reply.payload["claims"] if reply else [])]
                fixture_ids = fixture_ids_delivered((tr or {}).get("claims") or {}, delivered_ids, qtag)
                other_form = {rid: did for rid, did in fixture_ids.items() if rid != did and any(o["claim_id"] == did for o in outcomes)}
                if other_form:
                    rec["fixtures_served_under_other_id_form"] = other_form
                if kind == "genuine":
                    # how far each delivered claim went (extracted, eligible, attempted, completed, approved), each a list of its own
                    delivered_claims = SpecialistReport.model_validate(reply.payload).claims if reply is not None else []
                    rec["claim_measures"] = claim_measures(delivered_claims, outcomes, found, offered=frozenset((tr or {}).get("claims") or {}) | frozenset(fixture_ids.values()))
                if kind == "genuine" and tr:
                    rec["fixture_claim_text_sha256"] = dict(fixture_digests.get(sp.stem, {}))
                    # fixtures recorded under claim ids this parse does not deliver (in either form of a STEM id) are never
                    # served: say which
                    rec["fixtures_matching_no_delivered_claim"] = sorted(set(tr["claims"]) - set(fixture_ids))
                    # what became of every recorded translation: served, or lost and why
                    rec["fixture_coverage"] = fixture_coverage(tr["claims"], tr.get("claim_text_sha256") or {}, delivered_claims, outcomes, found, tag=qtag)
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
    # the delivery policy's decision for every genuine answer: a pass of its own, on a hub of its own, after the round's
    # records are complete (it adds no record and moves no transport count)
    deliveries = (delivery_pass(items, make_verify_fn, recorded_relays, records, overseer=delivery_overseer) if DELIVERY_PASS else
                  {"skipped": "the delivery pass is switched off (DELIVERY_PASS is False: a harness that replaces this module's hub or verifier "
                              "runs this round)", "tasks": [], "by_mode": {}, "errors": []})
    # with overseer agents configured, the same pass without them: the withheld baseline the configured decisions are read beside
    baseline = (delivery_pass(items, make_verify_fn, recorded_relays, records) if DELIVERY_PASS and delivery_overseer and delivery_baseline else None)
    # the specialist revisions (design section 53): a pass of its own, only when the round recorded the feedback its specialists
    # read; it adds no record and moves no transport count
    revisions = (revision_pass(round_dir, items, recorded_relays) if REVISION_PASS else
                 {"skipped": "the revision pass is switched off (REVISION_PASS is False)", "tasks": [], "checks": [], "errors": []})
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
           "deliveries": deliveries,
           **({"deliveries_baseline": baseline, "delivery_comparison": delivery_comparison(deliveries, baseline)} if baseline is not None else {}),
           "revisions": revisions,
           "failures": [r for r in records if not r.get("functional")], "records": records}
    # the separate measures, and the qualifications they raise (a run that lost expected translations says so)
    out["metrics"] = round_measures(records, translations, adjudications, task_record=task_record)
    out["qualifications"] = out["metrics"]["qualifications"]
    out["qualified"] = bool(out["qualifications"])
    # the overseer's configuration (rule overseer-beside): where it was found, and whether the operator replays without it on purpose
    out["overseer"] = {"found_beside": OVERSEER_FOUND_BESIDE is not None, "without_overseer": bool(without_overseer),
                       "passes_not_run": overseer_passes_not_run(out)}
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
    if out["overseer"]["passes_not_run"]:
        lines += ["", "Overseer configuration: " + ("replayed without the overseer on purpose (--without-overseer): " if without_overseer else
                                                    "NOT installed, and --without-overseer was not given, so the command line fails the run: ")
                  + ", ".join(out["overseer"]["passes_not_run"]) + " not run."]
    lines += [""] + delivery_lines(out["deliveries"])
    if baseline is not None:
        lines += [""] + delivery_baseline_lines(baseline, out["delivery_comparison"])
    lines += [""] + revision_lines(out["revisions"])
    lines += ["", "## Failures", ""] + ([f"- {r['file']} [{r['variant']}]: {'; '.join(([r['error']] if r.get('error') else []) + (r.get('failure_reasons') or [])) or ('status ' + str(r.get('status')) + ' codes ' + str(r.get('codes')))}" for r in out["failures"]] or ["(none)"])
    (round_dir / "summary.md").write_text("\n".join(lines))
    return out


def main(argv: list[str] | None = None) -> int:
    """Run one round and print its measures. Exit status 0, or 1 with ``--fail-on-qualification`` when the run is
    qualified (expected translations lost, served translations bound by claim id only, or adjudications that do not
    apply), so a translation-regression run fails instead of reporting figures for a different set of translations.
    ``--without-task-record`` replays without the task record (``run_round(..., task_record=False)``)."""
    ap = argparse.ArgumentParser(description="Feed a recorded arena round through the hub and write results.json and summary.md.")
    ap.add_argument("round_dir", type=Path, help="the round directory (specialists/, translations/, syntheses/, relayed/, adjudications/)")
    ap.add_argument("--fail-on-qualification", action="store_true",
                    help="exit with status 1 when the run is qualified, for a translation-regression run that must use every recorded translation")
    ap.add_argument("--without-task-record", action="store_true",
                    help="do not pass the task record to the translator (production passes it): the configuration of the replays before round 8's "
                         "clearance, for a comparison with them only; results.json and summary.md say so")
    ap.add_argument("--without-overseer", action="store_true",
                    help="replay where the overseer is not installed on purpose: its delivery pass and revision pass are recorded as not run and "
                         "the run exits 0; without it a pass not run because the overseer is not installed fails the run (exit status 1); "
                         "results.json and summary.md record the configuration")
    ap.add_argument("--fail-on-revision-gates", action="store_true",
                    help="exit with status 1 when the revision pass ran (the round holds feedback/) and one of its gates failed or it recorded an "
                         "error, so a feedback exercise whose specialists cannot be shown to have read the feedback as issued fails")
    ap.add_argument("--overseer-provider", metavar="MODULE:FACTORY",
                    help="configure the delivery pass's overseer agents with this provider factory (agent_id -> completion provider), run "
                         "through the overseer package's runner and verdict intake: the pass's decisions are reported beside the withheld "
                         "baseline of the same pass without overseer agents. Without it the harness calls no model")
    ap.add_argument("--overseer-pack", type=Path, metavar="ZIP",
                    help="the exported overseer knowledge pack the overseer agents are built from (with --overseer-provider); by default the "
                         "installed pack is exported to a temporary directory and loaded from its zip, as the deployed policy loads it")
    args = ap.parse_args(argv)
    rd = args.round_dir.resolve()
    if args.overseer_pack is not None and not args.overseer_provider:
        ap.error("--overseer-pack needs --overseer-provider")
    overseer = None
    if args.overseer_provider:
        try:
            overseer = delivery_overseer_config(args.overseer_provider, args.overseer_pack)
        except (ValueError, ImportError, OSError) as exc:
            ap.error(f"--overseer-provider: {exc}")
    res = run_round(rd, task_record=not args.without_task_record, delivery_overseer=overseer, delivery_baseline=overseer is not None,
                    without_overseer=args.without_overseer)
    print(json.dumps({k: res[k] for k in ("round", "transmissions", "functional", "functional_rate", "by_variant", "provider_dependent_translation_outcomes", "translation_outcomes_all_variants", "wall_s")}, indent=2))
    print("failures:", len(res["failures"]))
    dl = res.get("deliveries") or {}
    if dl.get("skipped"):  # a pass not run is said so, never printed as a pass that decided nothing
        print(f"delivery decisions (a separate measure): not run ({dl['skipped']})")
    else:
        print("delivery decisions (a separate measure):", ", ".join(f"{k} {v}" for k, v in (dl.get("by_mode") or {}).items()),
              f"| receipts identical to the genuine records': {dl.get('receipts_matching_genuine_records', 0)} of {dl.get('decided', 0)}",
              f"| delivery pass errors: {len(dl.get('errors') or [])}",
              f"| overseer-selected fallback: {'exercised' if dl.get('fallback_exercised') else 'NOT exercised (' + str(dl.get('fallback_not_exercised')) + ')'}")
        base = res.get("deliveries_baseline")
        if base:
            print("  without overseer agents (the withheld baseline):", ", ".join(f"{k} {v}" for k, v in (base.get("by_mode") or {}).items()),
                  f"| decisions that differ with the overseer agents: {len((res.get('delivery_comparison') or {}).get('changed', []))}")
    rv = res.get("revisions") or {}
    if rv.get("skipped"):
        print(f"specialist revisions (a separate measure): not run ({rv['skipped']})")
    else:
        print("specialist revisions (a separate measure):", f"answers revised {rv.get('answers_revised', 0)}, flaws fed back {rv.get('flaws_fed_back', 0)},",
              "gates:", ", ".join(f"{k} {'PASS' if v else 'FAIL'}" for k, v in (rv.get("gates") or {}).items()), f"| errors: {len(rv.get('errors') or [])}")
    ge = res["genuine_receipts_with_errors"]
    print("genuine transmissions, peer relays and syntheses with errors or warnings:", len(res["genuine_with_errors"]), "| mutation records with unexplained findings:", len(res["mutations_with_unexplained_findings"]))
    print(f"genuine records with an error-level finding: {ge['with_error_findings']} of {ge['genuine_records']}, {ge['with_error_findings_counted_functional']} counted functional (the rate does not judge whether a finding is true)",
          "| definitive verdicts other than ENTAILED displayed on genuine claims:", len(res["displayed_non_entailed_definitive_outcomes"]))
    print("recorded peer relays differing from the current parse:", sum(1 for c in res["recorded_relay_checks"] if not c["identical"]), "of", len(res["recorded_relay_checks"]),
          "| recorded relays exposing router-only fields to the dependent agent:", sum(1 for c in res["recorded_relay_checks"] if c.get("router_fields_exposed")))
    print("\n".join(line for line in measure_lines(res["metrics"]) if line))
    print("results written to", rd / "results.json", "and", rd / "summary.md")
    if res["qualified"] and args.fail_on_qualification:
        print("FAILED: the run is qualified (--fail-on-qualification):", ", ".join(q["code"] for q in res["qualifications"]))
        return 1
    if overseer_passes_not_run(res) and not args.without_overseer:
        print(WITHOUT_OVERSEER_FAILURE)
        return 1
    if args.fail_on_revision_gates:
        failing = revision_gate_failures(rv)
        if failing:
            print("FAILED: the revision pass's gates (--fail-on-revision-gates):", "; ".join(failing))
            return 1
    return 0


def overseer_passes_not_run(res: dict) -> list[str]:
    """The passes of the overseer this run did not run because the overseer is not installed (``deliveries`` and ``revisions``
    skipped for :data:`OVERSEER_NOT_INSTALLED`); a pass switched off by a harness (``DELIVERY_PASS``/``REVISION_PASS`` False) or a
    round with no ``feedback/`` is not among them."""
    return [name for name in ("deliveries", "revisions") if (res.get(name) or {}).get("skipped") == OVERSEER_NOT_INSTALLED]


def revision_gate_failures(rv: dict) -> list[str]:
    """What fails ``--fail-on-revision-gates``: every gate of the revision pass that failed and every error it recorded
    (nothing when the pass was not run because the round holds no feedback/: no feedback exercise ran; a pass not run for
    any other reason while the round holds feedback/ fails, since its gates were never decided)."""
    if rv.get("skipped"):
        return [] if str(rv["skipped"]).startswith("the round has no feedback/ directory") else [f"the revision pass was not run ({rv['skipped']})"]
    out = [f"gate {k} FAIL" for k, v in (rv.get("gates") or {}).items() if not v]
    out += [f"error: {e.get('error')}" for e in rv.get("errors") or []]
    if not rv.get("gates") and not out:
        out.append("the revision pass decided no gate")
    return out


if __name__ == "__main__":
    sys.exit(main())
