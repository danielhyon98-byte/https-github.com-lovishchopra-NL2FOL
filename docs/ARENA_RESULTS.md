# Arena results: isolated specialist agents communicating through the infrastructure

The arena is the contained environment in which real specialist agents, configured only
from their subjects' knowledge documents and isolated from the verification code (the English
and History specialists in rounds 1 to 6, sixteen specialists across fifteen IB subjects in
round 7), produce answers to router tasks; every output then crosses the hub exactly as it would in
production (`RouterHub` -> `TranslatorChannel` -> subject branch with integrity packs ->
engine), and independent overseer agents judge whether what the router received is what
the specialist said and whether every injected fault was named. The infrastructure is
code; the agents are its traffic. Harness: `scripts/arena/run_arena.py` (functional-rate
definition in its docstring), `scripts/arena/list_claims.py` (claims as transmitted),
`scripts/arena/relay_peer.py` (a delivered report forwarded to a peer specialist),
`scripts/arena/stress_arena.py` (replayed load).

A transmission counts as functional only when the hub produced a receipt without raising,
the receipt status is consistent with the input, and every translator output was decided by
the engine or rejected with diagnostics (never INTERNAL_ERROR). A genuine response must not be
REJECTED: every specialist file is treated as a genuine answer, so a deliberately broken input
that the hub correctly rejects (the r1-adv empty response) is reported as a failure, not
re-labelled. A response carrying an injected fault must show the expected finding, and since
round 4 that finding must name the injection: a finding of the expected code that names an
injected claim or quotes the injected words, and that the genuine record of the same task does
not already carry. Since round 5 the combinator's synthesis of each task (one synthesis per peer
group, citing every delivered report) is a transmission of its own, counted in the rate under the
same conservative rule: a synthesis of the delivered reports must be delivered (REJECTED is a
failure, never re-labelled) and no check on it may fail internally. Its errors and warnings are
listed with the genuine ones. Since round 7 every group of a round that carries syntheses has
exactly one synthesis record, whatever happened to its members, and it fails when a member was not
delivered; a quotation mutation of a task with a supplied text of its own must be refuted
(INT-REQ-003), not merely called unverifiable. A re-run parses every raw answer with the code as it stands; a
peer relay recorded by an earlier run is compared with that parse, not delivered in its place.
Translation outcomes depend on the translation provider and are reported separately from the
infrastructure rate.

Each round below gives its material, the overseers' verdict per lens, what they found, what the
fix round changed and the harness after it. The end of the file has the final verification, a
table of every round's verdicts, whether the 0.98 target was reached (it was not, in any round
from 1 to 7) and what remains open.

The harness rate does not judge whether a finding is true. A genuine transmission, peer relay
or synthesis whose receipt carries an error is still functional when the hub delivered it and
decided every check, whether the error names a real fault of the specialist or is false (the
round-6 hi-t12 receipt carried an engine-signed INT-SUBJ-001 that all three overseers judged
false, and was counted functional). Whether a receipt is right is what the overseers judge,
which is one reason their rates are lower. Since round 6, summary.md says this under its
headline: how many genuine, relay and synthesis records carry an error-level finding (each
named with its codes and claim ids) or warnings only, and that they are counted functional
(`genuine_receipts_with_errors` in results.json). It also names every definitive verdict other
than ENTAILED displayed on a genuine claim, with its claim id and what it rests on
(`displayed_non_entailed_definitive_outcomes`).

## Which measure each published number is

The numbers in this file measure different things and are never combined into one rate. Since the review of
12 October 2026 the harness reports them as separate measures (results.json `metrics`, summary.md 'Measures';
definitions in `scripts/arena/README.md`).

| Published number | Measure | What it does not say |
| --- | --- | --- |
| Harness counts: r1 30/30, r1-adv 150/151, r2 to r6 46/46, r7 162/162 (177/177 with the 15 STEM mutations added when STEM support merged); as run for the overseers, r1 20/22 and r1-adv 108/127, then 34/34, 41/41, 41/41, 41/41, 46/46 and 148/161 | Transport: the hub delivered and decided every transmission and named every injected fault | Whether a finding is true (r7: 18 of 44 genuine records carry an error-level finding and are counted functional), whether a translation is faithful, whether an answer is better. A replay of recorded material measures regression stability on that material, not generalisation |
| Lens rates, e.g. round 7: 0.532 (results audit), 0.4246 (communication fidelity), 0.7477 (adversarial live), 0.6384 (translation fidelity); the 0.98 target | Each overseer lens's verdict on its own question: receipts against their input; what the router received against what the specialist said; hostile variants; translations judged claim by claim | They are not transport rates, although the lens files name the field `infrastructure_functional_rate` |
| 143 of 224 translations faithful (round 7) | Translation fidelity, adjudicated by the round-7 translation-fidelity lens on the round-7 translations as they ran then, before the round-7 fix round | A figure for the current code: it has not been re-measured (no live translator was called) |
| A re-run of r7 serves 24 of the recorded fixtures, 200 match no delivered claim id; the re-keyed copy's 159 outcomes | Fixture coverage: how many recorded translations a replay can still use | Fidelity. Of the 24, 22 are served and 2 belong to delivered claims that are not eligible under the current policy (outcome NOT_ELIGIBLE, the provider never asked), so coverage is 22 of 224. The re-keyed copy is a reconstruction, not the recorded round |
| Translation outcomes on the genuine pass (for example r2: 21 AMBIGUOUS_TRANSLATION, 3 ENTAILED), genuine claims given no verdict (E108; E110 and E111 where a source states the figure; E112; stated precision; exactness), verdicts that stand with an advisory coverage warning (W110, W111), ENTAILED verdicts resting only on ungrounded premises, approvals resting on an unresolved dependency, claims whose release assessment permits release | Claim counts: what the recorded translations of attempted claims became in the current pipeline (completed when a definitive verdict is displayed; release permitted only by the release rule, apart from the formal status) | Fidelity, and anything about a live translator: the outcomes depend on the recorded fixtures |
| Overseer agents: 52 of 123 agent-scorable faults named, 49 of 83 accusations confirmed, 0 of 42 clean transfers falsely accused (round 7) | Overseer-agent detection against gold labels | The translation-fidelity lens found the gold labels of two translation fault classes mis-measured, so these figures carry that error |
| Suite totals (1855 passed after the round-7 fix round) | Test counts | Anything about the arena |
| `docs/STEM_RESULTS.md`: 38 of 38 injected faults named and no error on 46 correct answers; 293 of 293 on the 558-item corpus | Detection on answers written for the tests | Live arena results |

Replays with the separate measures (the code of this change, before the other fixes of the same review; copies of the
recorded rounds):

| Round | Transport | Fixture coverage | Translation fidelity | Claims: extracted / eligible / attempted / completed / approved |
| --- | --- | --- | --- | --- |
| r1 | 30 / 30 | 16 of 17 served (1 claim not eligible) | not adjudicated | 71 / 21 / 16 / 4 / 4 |
| r1-adv | 150 / 151 | 1 of 2 served (1 claim not eligible) | not adjudicated | 911 / 644 / 1 / 0 / 0 |
| r2 | 46 / 46 | 22 of 24 served (2 claims not eligible) | not adjudicated | 120 / 28 / 22 / 2 / 2 |
| r3 | 46 / 46 | 24 of 27 served (3 claims not eligible) | not adjudicated | 87 / 27 / 24 / 7 / 7 (all 7 rest on at least one ungrounded premise) |
| r4 | 46 / 46 | 25 of 27 served (2 claims not eligible) | not adjudicated | 100 / 27 / 25 / 8 / 2 |
| r5 | 46 / 46 | 17 of 20 served (3 claims not eligible) | not adjudicated | 90 / 23 / 17 / 6 / 6 |
| r6 | 46 / 46 | 27 of 28 served (1 claim not eligible) | not adjudicated | 93 / 28 / 27 / 15 / 15 |
| r7 | 177 / 177 | 22 of 224 served (200 claim ids no longer delivered, 2 claims not eligible) | not adjudicated in the recorded round; on a copy with the lens's 224 judgments bound to the fixtures they judged, 13 of the 22 judgments that apply are faithful and 202 do not apply | 475 / 260 / 22 / 6 / 6 |

Every run is qualified in its summary: each lost recorded translations (claims not eligible under the current policy,
and in r7 the 200 claim ids that changed), and every served translation is bound by claim id only, since no round
recorded `claim_text_sha256`. On every round the receipts, verdicts and per-record functional flags are identical to a
replay with the harness before the change. The 13 of 22 is not comparable with the 143 of 224: it covers the 22
translations the current parse still serves. On the tree that integrates every fix of the same review, the transport,
coverage and claim counts above are unchanged on every round (section 'Replays after the fixes of the external review
of 12 October 2026').

## Round 1 (four tasks: two English analytical paragraphs on a supplied extract, two History responses)

| Measure | Before fixes | After fixes |
| --- | --- | --- |
| Harness, genuine outputs and 5 fault mutations each (r1) | 20 / 22 functional (90.9%) | 22 / 22 (100%) |
| Harness, adversarial variants built from the same outputs (r1-adv: markdown, CRLF, zero-width, 530 sentences, 1,189-word bullet block, empty, fake receipt, contradictions, unbalanced quotes) | 108 / 127 (85.0%) | 126 / 127 (99.2%) |
| Overseer verdicts (results-audit / communication-fidelity / adversarial-live) | 0.909 / 0.909 / 0.850, 33 bugs (8 blockers, 15 majors, 10 minors) | round 2 below |

The one remaining r1-adv record is the empty response: the hub REJECTS it with INT-REQ-009
(the right outcome), and the harness's conservative "a genuine response is delivered" rule
counts that rejection as a failure. It is reported, not re-labelled.

What the round-1 overseers found and what changed (all fixed with regression tests):

- A from-memory label anywhere in a History answer suppressed the unverifiable-quotation
  finding for the whole report, so an invented quotation crossed the hub silently. The
  label now covers dates and figures only; quotations without a supplied text are always
  reported (CORE-SRC-003).
- An empty or over-limit answer raised out of the hub. Raw text the adapter cannot turn into
  a report is now REJECTED with INT-REQ-009; parsers respect the 4,000-character,
  512-claim and 64-support contract limits (overflow is folded into a tail claim and named).
- Markdown furniture (headings, numbered items, bullets, fences, emphasis, a byte-order mark)
  became claims, and a trailing one-line paragraph re-labelled every claim of the first
  paragraph. Shared pre-segmentation (`adapters/markdown.py`) strips the furniture while
  `original_response` stays verbatim; note sentences (from-memory labels, self-certification,
  task-setting notes) are roled `other` and never material.
- "percentage points" and year ranges were read as per-cent changes and chronology checks
  ignored relative clauses (false INT-SUBJ-001 errors on correct sentences). Fixed in the
  quantitative and chronology extractors.
- The synthesis relay never ran the entailment check its receipt announced; stale
  formalizations stayed in the cross-agent pool; conflict findings did not name reports.
  Fixed in the channel.
- A paragraph constraint such as "write one analytical paragraph" was not extracted; an
  unbalanced quotation mark silently dropped a quotation; a non-ASCII historian's name
  escaped the attribution check; a quotation-only sentence was emitted twice. All fixed.

## Round 2 (six tasks, including a History-to-English peer exchange through the hub)

Fresh outputs from the isolated agents: two English paragraphs on a sonnet and a novel
opening, two History responses (a famine, a crash) heavy with dated figures, and a peer
exchange: the History specialist's context paragraph was delivered to the router, forwarded
by the router to the English specialist (`specialist_report_forward/1.0`, checked against
the delivery), supplied to it as the document `peer:hi-p1`, and quoted by it in its own
paragraph; the hub then checked those quotations of the peer like any other.

| Measure | Value |
| --- | --- |
| Harness, genuine outputs, 5 mutations each and the peer relay (r2), with translator output for 24 eligible claims and a dummy combinator's syntheses | 34 / 34 functional (100%) |
| Translation outcomes (provider-dependent, reported separately) | 17 ENTAILED, 113 AMBIGUOUS_TRANSLATION, 0 INTERNAL_ERROR |
| Peer relay | delivered; a forward altered in transit or never delivered is refused (INT-HANDOFF-013) |
| Group synthesis for the peer exchange (both reports cited) | delivered with information-level ledger notes only |
| Round-1 sets re-run on the round-2 code | r1 22 / 22; r1-adv 126 / 127 (the empty response, correctly REJECTED) |
| Overseer verdicts (results-audit / communication-fidelity / adversarial-live) | 0.56 / 0.488 / 0.612; 49 bugs (2 blockers, 24 majors, 23 minors); every finding fixed with a regression test in the fix round below |

The harness rate and the overseers' rates differ because the overseers judge what the
harness cannot: they read every delivered payload against the specialist's text and
construct exchanges the harness does not (a specialist relaying a forged copy of a
colleague's report, a combinator changing a figure, a response that only echoes the
request, 600 arithmetic sentences, nested and mixed quotation marks). What they found, in
summary (the full reports with reproductions are kept with the round's material):

- Hand-off integrity: a specialist could relay an altered copy of a colleague's report
  under the colleague's name and overwrite the report the router held; relays were not
  checked against the plan's selected agents; the envelope sender was never bound to the
  payload owner; the same report id re-delivered with a different payload replaced the
  first silently.
- Receipt robustness: a report with about 440 arithmetic sentences made the receipt
  summary exceed its contract limit and the error escaped the hub.
- Fidelity of the arithmetic and chronology checks: month-year dates between the
  figures, shared units ("from 15 to 45 million"), per-thousand rates, word fractions and
  an asymmetric tolerance band let wrong figures pass or flagged correct ones; chronology
  was decided only for the first "after" in a sentence.
- Parsing fidelity: self-certification phrased outside the recognised vocabulary, forged
  receipt JSON and echoed requests became material claims; an evidence sentence with an
  inline from-memory parenthetical was demoted to a note; single-quoted, guillemet and
  mixed-mark quotations were invisible to the History branch; a quotation located in no
  document was attributed to the first one; a colleague's located words were reported as
  the quoter's own from-memory quotation.
- Combinator checks: a synthesis that changed a figure or a date was not named, and a
  synthesis citing two contradictory sources without disclosing the conflict passed.
- Request fidelity: an instruction sharing a sentence with a word limit was dropped;
  meta-text words counted against the word limit.

Each finding was fixed with a regression test before round 3 (the fix round below); the
round-3 verdicts are recorded here when they arrive.

## Round 2 fix round (three fixers on disjoint paths, the harness updated alongside)

The 49 findings were split by path between three fixers working at the same time, each
adding regression tests next to the code it owned (`tests/channel/test_round2_fixes.py`,
`tests/integrity/test_round2_integrity.py`, `tests/branches/test_r2_quant_chronology.py`,
`tests/adapters/test_overseer_round2.py` among them). The suite is 718 tests, all passing.

**Channel, integrity and translate.** Every relay now binds the envelope to the payload's
owner (INT-ENV-008 was defined but unreachable on the channel), so a specialist can no
longer relay a colleague's report under its own name, and the sender and recipient of a
relay must be parties the plan selected (a synthesis from an unselected combinator is not
delivered). A report id re-delivered with a different payload no longer overwrites the
report the router holds: the first delivery is kept and the later one is refused
(INT-HANDOFF-015); a superseded report still in circulation (forwarded, quoted as a peer
document, cited by a synthesis) is named (INT-HANDOFF-014). An agent id that is not the
request's addressee or not selected is rejected before parsing (INT-REQ-001 /
INT-HANDOFF-002) on every branch, so identity no longer depends on the adapter. A response
that restates the request is named and counts for no item (INT-REQ-011). Quotation grounding
gained tiers for nested marks folded to one class, a verse line break written " / ", and an
elision longer than the window: the words occur, so these are form differences
(INT-REQ-010, warning), never invented quotations; INT-REQ-003 now says in which supplied
texts the words were searched or in which other text they occur (misattributed). The
receipt summarises a report's formal checks as counts, so 440 arithmetic sentences no longer
overflow the summary contract and raise out of the hub. A translation is bound to the digest
of the claim text it read (`TranslationResult.claim_text_sha256`): the channel neither shows
nor pools an outcome attached to a claim whose text differs (INT-STALE-011), and the fixture
provider refuses a fixture produced for another text. The plan carries each agent's own task
type (`WorkPlan.agent_task_types`) and INT-HANDOFF-010 compares against it; the request
parser keeps an instruction that shares a sentence with a word limit and measures word
bounds over the answer proper, not the meta-text. The ledger names a synthesis that changes
or introduces a figure or date (INT-LEDGER-023) or drops one under an equivalence label
(INT-LEDGER-024).

**Quantitative and chronology checks, core pack, History adapter.** The from/to extractor
reads month-year dates between the figures, shared units ("from 15 to 45 million"),
per-thousand rates and word fractions ("a fall of about a half"), and its tolerance band is
symmetric around the computed value rather than the stated one; chronology is decided for
every ordering cue in a sentence ("after", "before", "followed", "preceded"), including a
subject's date set in an aside. The History parser and the core pack read quotations in
every mark style the English parser already read (single marks around two or more words,
curly, guillemet and mixed marks), so a single-quoted span with no supplied text is
recorded as an assumption and reported (CORE-SRC-003), an unbalanced mark is located and
the span it opens is named as unchecked (CORE-SRC-004), and a quotation credited to a named
source but located only in a different supplied text is a wrong credit (CORE-SRC-005, error
for a peer misattribution). A dated-figure sentence carrying the method's inline from-memory
label keeps its role and records the label as an assumption (so hi-t4's Dow sentence is an
eligible evidence claim again); judgement and link claims are wired to their supports; task
notes are notes; HI-STR-001 is not raised when the request asks only for an outline.

**English specialist, generic parser, shared markdown helpers, registry.** One shared set of
quotation helpers (`adapters/markdown.py`: spans in every mark style with the dangling mark
of an unbalanced text set aside, self-certification by vocabulary, by the semantic
self-subject rule and by JSON shape, pasted JSON blocks stripped, underscores inside words
kept) is used by the English parser, the generic parser and the core pack, so the parsers
and the hub say the same thing. The English parser takes the hub-stated agent id, treats
self-certifying, narrated and JSON-shaped sentences as `other` with no source refs wherever
they stand, records no source ref for the span a dangling mark opens, folds claims beyond
511 into a tail claim instead of rejecting the answer, and attributes a quotation to the
text its sentence names: a quotation located only in another text is ES-SRC-008 (error when
a relayed peer report is on either side). ES-SRC-003 is searched outside quotations and
counts only quotations not located in a supplied text, which removes the false finding on
every peer-exchange transmission; ES-STR-002 is suppressed when the request sets a word
count; ES-SRC-001 lists every text searched. The generic parser keeps the role of a
sentence with an inline from-memory label and treats a paragraph with a self-certifying
sentence as a note paragraph.

**Harness.** `run_arena.py` populates `WorkPlan.agent_task_types` from each group member's
own task type (the History peer of group p1 answers a `short_answer`; `relay_peer.py` builds
the same plan and records it); adds the mutation `invented_quotation_single` (the invented
words in single marks, expected INT-REQ-003 against a supplied text and CORE-SRC-003
without); records per claim outcome the interpretation's ambiguity flags, the translation
diagnostics and, for a verified problem, the engine status with the number of premises
relied on and how many of those are ungrounded or unverified; passes the fixture provider
the digest of the claim text each fixture was produced for (carried by the translations file
or captured from the genuine transmission) and records a refused stale fixture per claim as
`STALE_FIXTURE_REFUSED` (no verdict, not an infrastructure error); counts
`provider_dependent_translation_outcomes` over the genuine pass only, with the
distinct-claim counts beside it, and keeps the per-variant totals under
`translation_outcomes_by_variant`. `list_claims.py` prints each claim's assumptions and its
advisory self-report status under the existing columns and, with `--json`, the claim-text
digest. `stress_arena.py` counts a hub call that raises as the status `CRASH:<ExceptionType>`
and continues (`docs/STRESS_RESULTS.md`).

New codes since round 2: INT-REQ-010, INT-REQ-011, INT-STALE-011, INT-HANDOFF-014,
INT-HANDOFF-015, INT-LEDGER-023, INT-LEDGER-024, CORE-SRC-004, CORE-SRC-005, ES-SRC-008;
INT-ENV-008 is now raised on the channel; INT-HANDOFF-010 compares against the agent's own
planned task type.

Harness after the fix round (the same recorded outputs, one more mutation per text):

| Set | Result |
| --- | --- |
| r2: 6 genuine outputs, the peer relay, 6 mutations each (`altered_quotation` skipped for the two texts without a quotation), translator output for 24 eligible claims, the dummy combinator's syntheses | 41 / 41 functional (100%): genuine 6/6, peer_relay 1/1, invented_quotation 6/6, invented_quotation_single 6/6, altered_quotation 4/4, self_certification 6/6, wrong_arithmetic 6/6, chronology_error 6/6 |
| r1 re-run | 26 / 26 (100%), the new mutation included |
| r1-adv re-run | 150 / 151 (99.3%); the one failure is the empty response, REJECTED with INT-REQ-009, which the harness's "a genuine response is delivered" rule counts as a failure rather than re-labels |
| Peer exchange on r2 | the History peer's request, report and forward carry `short_answer`; the relay is delivered with no finding; the single-quoted invented quotation of the peer-dependent English answer is named INT-REQ-003 against `doc-ozy` and `peer:hi-p1` |

Translation outcomes after the fix round, counted over the genuine pass (each eligible claim
with a fixture once; the earlier figures of 17 ENTAILED and 113 AMBIGUOUS were the same
claims repeated across the mutation variants):

| Set | Distinct claims | Outcomes | What the ENTAILED verdicts rest on |
| --- | --- | --- | --- |
| r2 | 24 | 21 AMBIGUOUS_TRANSLATION, 3 ENTAILED, 0 INTERNAL_ERROR | en-t3 p3-point: 7 premises relied on, 3 ungrounded; en-t4 p2-point: 5 relied on, 2 ungrounded; hi-p1 h1.1: 5 relied on, all 5 ungrounded (from-memory dates). One of the three rests only on ungrounded premises |
| r1 | 17 | 12 AMBIGUOUS_TRANSLATION, 5 ENTAILED | four of the five rest only on ungrounded premises (specialist inferences and assumptions); the fifth relies on 5 premises of which 4 are ungrounded |
| r1-adv | 2 | 2 INVALID_FORMALIZATION | the one r1-adv fixture was produced under the request id `req-hi-t1`; since variants became separate hub tasks the request is `req-hi-t1-contradiction-figures`, so the pipeline rejects the problem's request id with a diagnostic, as it should; the fixture is reported, not patched |

Across every r2 variant the totals are 139 AMBIGUOUS_TRANSLATION, 19 ENTAILED and 3
STALE_FIXTURE_REFUSED: in the `altered_quotation` variants of en-t3, en-t4 and hi-t3 the
altered sentence is a claim with a fixture (p1-s01, p2-point, h1.6), the claim's text digest
no longer matches the fixture's, and the provider refuses it. Every AMBIGUOUS record now
carries the flags the translation declared (for hi-t3 h1.1: "to a large extent, though not
wholly" is a degree judgement with no stated measure; the catastrophe link is a specialist
link the figures do not show; the counter-case is not weighed beyond the persistence
criterion), so the reason is in the record, not only the status.

Honesty notes, unchanged by the fix round: translation outcomes depend on the translation
provider (here fixtures written for the genuine outputs) and are reported apart from the
infrastructure rate; an ENTAILED verdict says only that the conclusion follows from the
stated premises under the encoding, and the record now says how many of those premises are
ungrounded, which for the History paragraph is all of them; an AMBIGUOUS_TRANSLATION is never
shown as verified. The genuine English answers, set out in four blank-line blocks, carry
INT-REQ-005 against the request's "one analytical paragraph", as they did before the fix
round; the receipt words it as a block count and the answer is delivered. The stress re-run after the fix round is in
`docs/STRESS_RESULTS.md`; the per-cycle cost rose because every excerpt is now located in
every supplied text for the attribution check.

## Round 3 (six fresh tasks, including an English-to-History peer exchange)

Fresh outputs from the isolated agents: English paragraphs on Blake's 'London' (with its
original spellings) and the opening of Pride and Prejudice (dialogue inside the extract), History
responses on the Cuban Missile Crisis (everything dated within one month) and German
hyperinflation (figures in trillions, exchange rates, inline from-memory labels), and the reversed
peer exchange: the English specialist's paragraph was delivered to the router, forwarded to the
History specialist with the forward contract, supplied to it as the document peer:en-p2 and quoted
by it; the group synthesis cited both reports.

| Measure | Value |
| --- | --- |
| Harness, genuine outputs, 6 mutations each and the peer relay (r3) | 41 / 41 functional (100%) |
| Round-3 overseer verdicts (results-audit / communication-fidelity / adversarial-live), on the round-2 fixes | 0.727 / 0.769 / 0.871 (round 2: 0.56 / 0.488 / 0.612); 44 of 49 round-2 findings confirmed fixed; 37 new findings (17 majors, 20 minors) |

What the round-3 overseers found and what the fix round changed (all with regression tests):

- Attribution on the History branch: a from-memory slogan in quotation marks had been credited
  to the first supplied text (the peer's paragraph) and faulted as a misquotation of the colleague.
  An unlocated quotation is now attributed only to a text the sentence names, otherwise it carries
  no source reference and is reported as unverifiable (CORE-SRC-003); a reporting clause ("The
  English specialist argues that Blake presents ... '...'") credits the outer speaker.
- Notes: sentence-initial and comma-bounded from-memory labels had demoted dated evidence to
  notes; only an empty core is a note now, and only the self-certifying sentence of a paragraph is
  demoted, never the whole paragraph (which had let one sentence evade verification of everything
  around it). A note sentence is never a paragraph's point and never counts toward request
  coverage; an answer with no material claim is INT-REQ-012.
- Chronology: dates in the same month were compared at month resolution and a true order was a
  violation; day-level and year-only tokens, context years for day-month dates, and "undecided"
  for equal resolution replace that. Arithmetic: noun phrases after units, trillions, thousands
  separators and word folds, year ranges, figures in words, signed changes, and incomparable units
  skipped; one abbreviation-aware sentence splitter ("c. 200 million") shared by the History
  parser and the packs.
- Combinator fidelity: swapped dates or figures between events (same tokens, different facts)
  are now INT-LEDGER-023; notes leave the unaccounted-claim count.
- Hand-off: an echo of the request can no longer supersede a genuine report; identical content
  re-delivered under one report id is a duplicate (INT-ENV-001), a changed payload is
  INT-HANDOFF-015; a claim with another report's provenance is INT-HANDOFF-012; stale-forward
  findings distinguish an excerpt that no longer occurs from one never located.
- Quotation forms: JSON pasted into prose no longer swallows the sentences around it; dialogue
  copied with marks inside marks is read as nested marks; stanza breaks written with slashes and
  long elisions are located and reported as form differences; claims folded beyond the contract
  limit keep their quotations checked and the receipt names what was folded (INT-REQ-013).

Harness after the fix round: r3 41 / 41, r2 41 / 41, r1 26 / 26, r1-adv 150 / 151 (the empty
response), with no genuine transmission carrying an error-level finding in rounds 1 to 3. The
round-4 overseer verdicts are recorded below.

## Consolidation pass before the round-4 verdicts

After the round-3 fix round and before the round-4 overseers judged, one consolidation pass dealt
with repeated work in quotation location, a diacritics gap and attribution rules that differed
between branches. Every change was checked with the harness on copies of r1, r1-adv, r2, r3 and r4.

- **Performance (`translate/grounding.py`, `adapters/sources.py`).** Every parse and check
  normalised each supplied text again and located the same excerpt in the same document many
  times. In one English hub transmission with a poem and a peer report, the same
  excerpt-in-document question was computed up to 12 times, and the uncached forms built Python
  int lists of offsets. A thread-safe `BoundedLRU`, bounded by entry count and by total
  characters, now holds each text's lazily built forms (`TextForms`: normalised, quote-folded,
  slash or stanza form, line-break marks dropped and its casefold, diacritics-folded) with 4-byte
  offset arrays. It is keyed by (document id, sha256 of the text), at most 64 entries and 2M
  characters. `locate_quotation`, `locate_quotation_inexact`, `locate_long_elision` and
  `find_quotation` are memoised per (function, excerpt, sha256), at most 16,384 entries and 8M
  characters, and `check_excerpt` per (excerpt, document id, sha256). The new optional
  `document_id` keyword never changes an answer; `clear_grounding_caches()` and
  `clear_excerpt_cache()` empty the caches. No finding changed: on the copies, the harness results
  were identical record for record to the baseline (codes, findings, subject findings, formal
  checks, coverage, outcomes and summaries).
- **Diacritics.** A quotation that differed from the supplied text only in its accents ('Bayardo
  San Román' against 'Bayardo San Roman') was reported as not found, with INT-REQ-003 and
  ES-SRC-001 errors. A diacritics tier in `locate_quotation_inexact` folds both sides (NFKD,
  combining marks dropped, offsets kept) and finds contiguous and elided matches. The difference
  is stated ("differs in diacritics ('Román' where the document has 'Roman')"), so the quotation
  is a located form difference: INT-REQ-010 from the channel and an ES-SRC-006, HI-SRC-001 or
  GEN-SRC-003 warning from the packs. An excerpt that differs only in how its accents are encoded
  (precomposed against combining) has the same letters and is a normalised match, never a
  diacritics warning. CORE-SRC-001 no longer calls a located form difference 'not found'.
- **One attribution rule.** The English and generic parsers credited a quotation that no text
  holds, in a sentence that names no text, to the first supplied text; the History parser credited
  none. All three now use `sources.attribute_excerpt`: the text that holds the words wins (in any
  form `check_excerpt` recognises); failing that, a text the sentence names is credited whether or
  not it holds the words; otherwise the claim has no source reference and the assumption
  'quotation with no supplied text to check it against' is recorded. The English branch keeps one
  extra step: when the sentence names no text, the quotation is credited to the one literary text
  under analysis if there is exactly one (a peer report never is). Without that step, a what-if
  harness run of the strict rule on copies dropped r1 from 26 to 24, r1-adv from 150 to 140, r2
  from 41 to 39, r3 from 41 to 38 and r4 from 41 to 38: 20 altered-quotation records of a single
  poem would have lost INT-REQ-003 for a CORE-SRC-003 warning. CORE-SRC-003 now also reads the
  parsers' recorded uncredited assumptions, so a quotation left without a source reference always
  reaches it, whatever its length.
- **Long elision on the generic branch.** A located long elision was an error-level GEN-SRC-001.
  Every located status other than exact, joined and elided (inexact, long elision, diacritics) is
  now a warning, and the error covers only not found, no document, no texts and empty.
- The package READMEs and parser docstrings were brought in line, and the stress result files
  that a `-m stress` run had overwritten were restored.

## Round 4 (six fresh tasks, including a History-to-English peer exchange)

Fresh outputs from the isolated agents: English paragraphs on Wordsworth's 'Composed upon
Westminster Bridge' (personification and the turn) and on a comic narrator's voice in a novel
opening, History responses on the Treaty of Versailles and Weimar instability (to what extent) and
on the 1929 crash and German unemployment (dated and quantified), and a peer exchange: the History
specialist's context paragraph on London in 1802 was relayed through the hub to the English
specialist as the document peer:hi-p3 and quoted in its reading of the sonnet's 'smokeless air'.

| Lens | Rate | Round-3 findings confirmed fixed / still open | New findings (blocker / major / minor) |
| --- | --- | --- | --- |
| results-audit | 0.387 | 10 / 2 | 0 / 10 / 5 |
| communication-fidelity | 0.575 | 8 / 0 | 0 / 6 / 6 |
| adversarial-live | 0.89 | 17 / 2 | 1 / 10 / 6 |

As run for the overseers, the harness counted 41 / 41 transmissions functional. Its one genuine
receipt with an error-level finding was hi-t8 (INT-CONFLICT-001), which the results audit showed
to be false. No lens reached 0.98. The round brought 44 new findings (1 blocker, 26 majors, 17
minors).

What the round-4 overseers found:

- **The hub could be crashed or stalled.** A lone UTF-16 surrogate in raw text (a truncated emoji
  arriving as "\ud83d") raised UnicodeEncodeError out of `RouterHub.receive` on both branches: the
  round's blocker. Brace-like text made the hub quadratic, because every '{' or '[' started a scan
  to the end of the text, so a short answer could stall it.
- **False errors on correct statements.** hi-t8's INT-CONFLICT-001 was a contradiction wholly
  inside one claim's literal encoding of 'roughly 60 per cent' (its own premises give 63.2 per
  cent). The unsat core was not claim-minimal, so the error was charged to an innocent claim that
  restated the figures, and the faithful synthesis was then given INT-CONFLICT-002 for not
  disclosing it. Intransitive 'followed in July 1922' was read as an order between two events; a
  bound qualifier separated from its fold word by an article was dropped; a shared unit carried
  the second figure's scale onto a first figure with its own unit; word bounds counted '1.9' and
  '100,000' as two words each (hi-t8 measured 191 words against 186).
- **Stated relations neither decided nor reported undecided:** a second from/to after ', and',
  chained rises, a relation stated in the sentence after its figures ('grew by roughly 60 per cent
  that year'), the qualifier 'near', and orders written 'came earlier than', 'prior to' or
  'predated'. In a sentence with two ordering cues, the second relation was paired with the first
  cue's object, so the engine certified an order the specialist never stated.
- **Roles, notes and self-reports.** A sentence whose core kept a label word was demoted wholly to
  a note; a disclaimer ('should be checked before they are cited') was recorded as a
  self-certification; self-certifications outside the vocabulary ('Z3 proved the argument above')
  passed as content on both branches. The judgement the request asked for (hi-t8 'The turning
  point was 1930.') arrived as non-material evidence that a combinator could drop. HI-STR-003
  contradicted the parser's own role, and an English concluding claim without one of eleven listed
  signposts was delivered as supporting.
- **Quotations.** Single-quoted quotations containing an apostrophe (don't, Scrooge's, Ne'er) were
  not read at all. A correct quotation with a bracketed elision ('[...]') was reported as invented.
  A quotation held by no text, in a sentence naming two sources, was credited to none (a regression
  of the round-3 fix). CORE-SRC-005 named every quotation of the sentence, not just the
  misattributed one.
- **Combinator and peers.** A synthesis could reverse or re-pair what its sources said with no
  finding: the ledger compared bare numerals only, so figures in words were invisible, a verdict
  re-paired to a figure the sources state elsewhere passed, and a merged claim could drop a dated
  statement. A peer's figure misreported in an unquoted paraphrase ('close to two million' for
  'close to a million') was not named.
- **Bookkeeping and the harness.** A relay the channel rejected was still recorded as transmitted,
  and a specialist's documented hand-off of its own report to the combinator was called a
  duplicate. The harness counted a mutation functional whenever the expected code appeared
  anywhere on the receipt.

What the fix round changed (fixers on disjoint paths, regression tests beside each change; 42
findings reported fixed; commit a2d874d):

- **Hub robustness.** Lone surrogates are REJECTED with INT-REQ-009 naming the offsets. JSON spans
  are found in one linear pass (`markdown.find_json_spans`, `bracket_match_ends`, fuzz-checked
  against the old scan on 30,000 texts with no difference), and a keyed block nested beyond the
  recursion limit no longer raises. The History splitter's own scan stayed quadratic until
  round 5.
- **Conflicts attributed claim-minimally.** Each claim of a multi-claim core is tested alone. A
  claim that refutes itself is INT-CONFLICT-005 (a warning under an assumed reading) and the rest
  is re-checked, so hi-t8's false error became a warning on h1.5 with no disclosure demanded. A
  conflict between two different claims where one is AMBIGUOUS_TRANSLATION stays an error that
  requires disclosure, on purpose: otherwise almost no arena conflict would need disclosure.
- **Arithmetic and chronology.** A derived figure, trend or superlative that no engine problem can
  be built for is named by the new structural warning CORE-QNT-001 (the arithmetic twin of
  CORE-CHR-001). New formal-check kinds `series_monotonic` and `series_extreme` were added; 'that
  year' is read as the single year of the nearest earlier sentence, and a check built across
  sentences says so (`basis`). Request word bounds count a figure as one word.
- **Notes and self-reports.** A note is only a sentence whose core is empty once its labels are
  set aside, read with quotations masked. A disclaimer is a note, never a self-certification.
  Self-certification now covers 'I have checked', 'all of these figures have been verified', 'can
  be relied upon', 'no errors were found' and Z3, the engine or the hub 'proved' or 'accepted' the
  answer. The requested judgement is recognised by a fixed verdict vocabulary (turning point,
  decisive year, most important, mattered most, watershed). The English parser reads 'Read
  together, ...', 'Taken together, ...' and similar openers as links, and a CR-only break as a
  paragraph break.
- **Quotations and attribution.** Single marks are paired by context, so an apostrophe inside a
  word or an aphetic form is not a mark. Bracketed and parenthesised elisions are ellipses
  (found_elided). `attribute_excerpt` takes the sentence: a quotation held by no text, in a
  sentence naming several, is credited by the governing possessive, else the speaker of the nearest
  reporting clause, else the nearest named text (`governing_document`), never to none.
- **Channel and ledger.** New INT-REQ-014 (warning: a figure or date credited to a relayed peer in
  unquoted prose that the peer does not state), INT-LEDGER-025 (error: a synthesized quotation that
  no text in scope holds) and INT-LEDGER-026 (warning: a lexical reversal of a copied statement).
  INT-LEDGER-023 reads figures in words, scale words and one-sided re-pairing; INT-LEDGER-024
  covers merged and generalized claims; INT-SYNTH-012 is raised on the channel's synthesis
  receipt. A hand-off to a new recipient is no duplicate, and a refused relay is not recorded.
- **The harness** (`scripts/arena/run_arena.py`, regression tests in
  `scripts/arena/test_arena_rules.py`, run by path as
  `python -I -m pytest -q scripts/arena/test_arena_rules.py`). The results audit found that the
  harness's own rule hid wrong receipts: hi-p3's genuine text already raises CORE-SRC-003 for its
  own 'smokeless air', so its three quotation mutations would have passed even if the injected
  quotation had not been named. Findings a mutation carried beyond the genuine record were never
  reported, and the summary listed only the error codes of genuine transmissions, with no claim
  ids, messages or warnings. What changed:
  - *The expected finding must name the injection.* Each mutation knows what it injected (the
    invented words, the altered quotation, the self-certification, the false arithmetic, the false
    order). A delivered claim whose text or quotation excerpt carries those words is an injected
    claim (`injected_claim_ids`). A mutation is functional only when a finding of the expected code
    (for the self-certification, one of the self-report codes) names an injected claim, quotes the
    injected words or, for the self-certification paragraph, names its place ('paragraph 5,
    sentence 1'), and the genuine record of the same task does not already carry that finding.
    The findings that qualified are kept as `named_by`; a failing record says why
    (`failure_reasons`).
  - *Findings beyond the genuine record are reported.* Each mutation record lists the findings the
    genuine record does not carry and that do not name the injection (`unexplained_findings`; a
    genuine finding that changed keeps its old message), and the errors and warnings of the
    genuine record that the mutation lost (`baseline_findings_absent`). A crossed word bound
    carries the genuine measurement and the number of words the mutation added, so it can be
    checked by subtraction (hi-t8: 186 genuine words + 17 appended = 203 measured). These are
    listed in results.json (`mutations_with_unexplained_findings`) and summary.md; they do not
    change the rate.
  - *The genuine section carries every error and warning* of each genuine transmission and peer
    relay, with its claim ids and message (`genuine_with_errors`: `codes` are the error codes,
    `warning_codes` the warning codes, `findings` the findings).
  - *A peer-dependent task's mutations are checked against the same pool as its genuine reply.* On
    each mutation's own hub task the peer's genuine report is now verified with the peer's own
    translations, as in the genuine pass. Before, it was verified with the dependent task's
    fixtures, so the peer contributed nothing to the cross-agent pool and every r2 en-p1 mutation
    silently lost the genuine cross-agent INT-GLOSSARY-005 between h1.1 and the English claims.

Left open by the round-4 fix round: the History splitter's own JSON scan (`strip_json_spans`)
stayed quadratic (1,000 JSON fragments took 20 s, 5,000 nested braces 46 to 118 s), with the
linear replacement handed to its owner; INT-SUBJ-001 carried no claim ids and quoted only the first
160 characters of a long statement; HI-STR-004 still split decimals; the recorded r4 peer relay
predated the parser fix; a synthesis that credits the History specialist's figure to the poet had
findings, but none named the misattribution; ISO dates such as 1923-01-11 stayed undecided. New
warnings appeared on genuine answers, all honest: hi-t7 CORE-CHR-001 (a relation stated across
sentences), r2 hi-t4 CORE-QNT-001 ('fell by roughly a third' with no base figures) and an
information-level HI-STR-003 on hi-p3.

Harness after the fix round. The same recorded rounds under the stricter rule, on the code as it
stood during the round-4 fix round (the channel, History and English fixes were landing at the
same time):

| Set | Before the harness fix | After |
| --- | --- | --- |
| r4 | 41 / 41 | 41 / 41; every quotation mutation of hi-p3 is named on the injected claim, not by the genuine CORE-SRC-003 |
| r3 | 41 / 41 | 41 / 41 |
| r2 | 41 / 41 | 41 / 41 |
| r1 | 26 / 26 | 26 / 26 |
| r1-adv | 150 / 151 | 148 / 151 |

The two new r1-adv failures were real receipt gaps that the old rule hid. hi-t2-long-bullets-nopunct
is a 6,500-character bullet block with no sentence punctuation, so the wrong_arithmetic and
chronology_error sentences join its last bullet. The History parser delivers that bullet as claim
h2.62, but the formal check read the whole block as one sentence. INT-SUBJ-001 was then raised with
no claim ids and quoted only the first 160 characters of the block, so nothing on the receipt said
which statement was false. The harness rule was not loosened to recover the rate; the round-5 fix
round closed the gap (below). The empty response is still the third failure.

## Round 5 (six fresh tasks, including an English-to-History peer exchange)

Fresh outputs from the isolated agents: English paragraphs on Carroll's 'Jabberwocky' (direct
speech and invented words) and on lines 1-32 of Marvell's 'To His Coy Mistress' (hyperbole and the
turn at 'But at my back'), History answers on Stalin's Five-Year Plans (one body paragraph, to what
extent, 1928-1941) and on the growth of Britain's railway network from 1830 to 1870 (dated and
quantified, with a judgement on the most decisive decade), and a peer exchange. In that exchange
the English specialist's paragraph on Hardy's 'The Man He Killed' (1902) was relayed through the
hub to the History specialist as the document peer:en-p4, and the History specialist outlined the
Second Boer War context for it.

| Lens | Rate | Round-4 findings confirmed fixed / still open | New findings (blocker / major / minor) |
| --- | --- | --- | --- |
| results-audit | 0.366 | 13 / 4 | 0 / 7 / 8 |
| communication-fidelity | 0.617 | 12 / 0 | 0 / 8 / 7 |
| adversarial-live | 0.79 | 16 / 3 | 0 / 12 / 3 |

As run for the overseers, the harness counted 41 / 41 functional, and the genuine receipts carried
warnings only (hi-t9 INT-GLOSSARY-005 five times, hi-t10 INT-GLOSSARY-005, hi-p4 CORE-SRC-003). No
lens reached 0.98. The round brought 45 new findings (0 blockers, 27 majors, 18 minors).

What the round-5 overseers found:

- **Stated relations unchecked or mis-checked.** Relations other than per-cent, point, fraction and
  fold changes (hi-t10's own 'added roughly 4,500 miles'; 'about 1,500 by 1840 and about 6,000 by
  1850') and chronology other than before/after cues (a reversed span) were neither decided nor
  reported undecided. 'nearly doubled' and 'almost' were read as a two-sided 5 per cent band, so a
  correct x1.88 got an engine-signed INT-SUBJ-001 and some false statements were ENTAILED.
- **Findings that name no claim.** INT-SUBJ-001 and INT-SUBJ-002 never carried claim ids (all 455
  in the adversarial overseer's runs) and quoted the statement from its start, cut at about 160
  characters.
- **Roles.** The verdict the request asked for, when not worded like the round-4 example ('The
  1840s were the most decisive decade.'), arrived as non-material analysis. A provenance sentence
  ('The historical setting is my own addition, not part of that paragraph.') became hi-p4's
  material point. Every English answer delivered its concluding claim as supporting, and a
  from-memory figure with no date was delivered at certainty 'established'.
- **Self-certifications** outside the enumerated subject and predicate shapes still passed as
  content on both branches.
- **Words credited across agents.** The History specialist could credit the English specialist's
  own words to Hardy or to 'the poem', which it had not been supplied, with no finding. The History
  branch still had the residual of the round-4 two-source attribution bug, and in a structured
  report nothing checked the quotation in a claim's text against its source reference's excerpt.
  Two punctuation differences (em dashes typed as spaced hyphens among them) turned a correct
  quotation into an invented one.
- **Combinator.** A merged claim could re-date a figure, move a decade (decades were not dates to
  the ledger), reverse a degree verdict or change who holds a view, with only an information note.
  Small counts written in words were invisible, a dropped from-memory label was not named, and a
  synthesis id could be reused with other content and both syntheses were delivered.
- **Glossary, request and hub.** INT-GLOSSARY-005 compared glosses as strings, which produced every
  genuine warning of the round. 'about N words' was read as a maximum only, the round-3
  request-echo finding was still open, and HI-STR-004 still split decimals. The History splitter's
  JSON scan was still quadratic; a payload that is not a model (a JSON mapping, None) raised out of
  `relay()` and `receive()`; a relay's sender role was whatever the caller asserted.
- **Harness.** The combinator's synthesis was not a transmission of its own, and a re-run delivered
  the payload a recorded relay held instead of the current parse.

What the fix round changed (39 findings reported fixed; commit 3147d08):

- **Formal checks name their claim.** `FormalCheck.claim_ids` is filled for every arithmetic and
  chronology check, and INT-SUBJ-001 and INT-SUBJ-002 carry those ids and quote the clause the check
  was built from. The two r1-adv bullet-block mutations exposed by the round-4 rule are named on
  their claim again, so r1-adv is back to 150 / 151.
- **Arithmetic.** More stated relations are decided by the engine, one check per stated relation so
  that each finding names its own pair. 'nearly' and 'almost' approach a figure from below (at
  least 85 per cent of it), so 'nearly a doubling' holds for x1.88 and fails for x2.1.
- **Roles.** A sentence about how the answer was composed is a note (`is_provenance_note`, shared
  through `markdown.split_note_clauses`, so it is also left out of word counts). The verdict rule
  is wider. Structural self-certifications ('Every mileage figure above has been checked',
  'Nothing in this answer needs checking') are roled `other` with the advisory status on every
  parser, which the router sees as INT-HANDOFF-006 (and ES-META-001 on English). The English
  splitter ends a sentence after a sentence-final possessive.
- **Attribution across agents.** `sources.quotation_credit`, `credited_agents` and
  `peer_prose_span` read who a sentence credits. New INT-REQ-015 (error): a quotation credited to a
  source the agent was not supplied, whose words occur only in a relayed peer report's own prose.
  The History parser passes the sentence to `attribute_excerpt`, so an altered quotation of the
  colleague in a reporting clause is refuted with INT-REQ-003.
- **Ledger and hand-off.** New INT-LEDGER-027 (warning: a from-memory label dropped). INT-LEDGER-023
  reads decades and small counts in words; INT-LEDGER-024 is judged per source over every
  synthesized claim citing it; INT-LEDGER-025 names a quotation credited to a text that does not
  hold it; INT-LEDGER-026 reads degree, comparative, order, target and direction reversals,
  negations, replaced content words and a view credited to the wrong specialist. INT-HANDOFF-015
  refuses a reused synthesis id, and INT-ENV-007 an infrastructure role asserted by an id that does
  not hold it. INT-GLOSSARY-005 compares gloss content, not strings, so the hi-t9 and hi-t10
  genuine warnings are gone.
- **Request and hub.** 'about N words' is bounded on both sides (0.9N to 1.1N). The channel
  validates or rejects any payload (a mapping, None) instead of raising, and the History splitter's
  JSON scan uses the linear matcher.
- **The harness.** The results audit and the adversarial overseer each found a way the harness hid
  what the hub did:
  - *The combinator's synthesis is a transmission of its own.* It had been kept inside the genuine
    record of the group's last task: not counted, not judged, and absent from
    `genuine_with_errors` and summary.md. Its findings were also kept without claim ids and cut to
    300 characters. So the r5 summary did not show the warnings the overseers judged false on the
    hi-p4 and hi-t10 syntheses. Each synthesis relay is now a record of variant `synthesis`,
    counted in the rate and in `by_variant`. It is functional when the hub returned a receipt
    without raising, the synthesis was delivered, and no check on it failed internally
    (INT-SYNTH-013, or a joint check left undecided with INTERNAL_ERROR). A round with syntheses
    but none for a delivered group records that group's synthesis as a failure. Every error and
    warning of a synthesis is listed in `genuine_with_errors` and summary.md with its claim ids and
    full message. The genuine and peer-relay records now keep full messages too; mutation records
    still cut theirs to 300 characters.
  - *A re-run parses every raw answer with the current code.* For a peer group's source task, the
    genuine pass used to deliver the payload `relay_peer.py` had recorded, so a re-run showed
    whatever parser had run the relay. The genuine pass now delivers the current parse of
    `response_text`; the recording is used only for the document the dependent agent read
    (`peer:<task>`, its `original_response`). Each recorded relay is compared with the current
    parse (`recorded_relay_checks`), giving the payload fields and claims that differ with both
    values and ignoring `created_at`. A synthesis whose group has a differing recording names it
    (`recorded_relays_differing`), because the combinator wrote that synthesis against the
    recorded claims.

Left open by the round-5 fix round: `RouterHub.receive` still raised for a JSON mapping received
without ids (fixed in round 6); 'more or less than any other year' is reported CORE-QNT-001 (only
decade superlatives are decided); CORE-SELF-001 still searched only the old self-certification
vocabulary; the recorded r2 and r4 relays and the r5 relay and p4 synthesis predate parser changes
and were not re-recorded (after the en-p4 possessive split, its claim ids from p1-s03 on shift by
one, so the recorded p4 synthesis no longer cites p1-s08 and its receipt carries INT-LEDGER-002).

Harness after the fix round, on the code as it stood during the round-5 fix round (package fixes
were landing at the same time; the figures before the fix round began were r1 26 / 26, r1-adv
148 / 151, r2 to r4 41 / 41):

| Set | Before the harness fix | After |
| --- | --- | --- |
| r5 | 41 / 41 | 46 / 46: the 5 syntheses are counted, all delivered. The recorded relay of en-p4 equals the current parse |
| r4 | 41 / 41 | 46 / 46. The recorded relay of hi-p3 differs from the current parse: h1.1's self-report status, h1.8's role, materiality and supports, and `unresolved_issues`. hi-p3's genuine record and en-p3's forward no longer carry the stale INT-HANDOFF-006. The group synthesis now carries INT-LEDGER-002 on h1.8, which the current parse makes a material link the recorded synthesis does not account for; its record names the differing relay |
| r3 | 41 / 41 | 46 / 46. The recorded relay of en-p2 equals the current parse |
| r2 | 41 / 41 | 46 / 46. The recorded relay of hi-p1 differs: h1.2's certainty (established, now probable) and the wording of its assumption. The group synthesis names the differing relay |
| r1 | 26 / 26 | 30 / 30: the 4 syntheses are counted |
| r1-adv | 150 / 151 | 150 / 151: no syntheses; the one failure is still the empty response, which the hub REJECTS with INT-REQ-009 |

Apart from those two r4 records, every genuine, peer-relay and mutation record kept the same
status and findings, and every synthesis kept the same status and codes.

## Round 6 (six fresh tasks, including a History-to-English peer exchange)

Fresh outputs from the isolated agents: English paragraphs on the opening of Jane Eyre (reported
and direct speech) and on Herbert's 'Love (III)' in its 1633 spelling (unmarked dialogue, long
and short lines), History answers on the Marshall Plan and Western European recovery from 1948
to 1952 (one body paragraph, to what extent, money figures) and on the pace of decolonisation in
Africa from 1957 to 1968 (dated and quantified, with a judgement on the decisive year), and a
peer exchange. In that exchange the History specialist's context paragraph for Emma Lazarus's
'The New Colossus' (immigration in the 1880s, the Chinese Exclusion Act, the Statue's dedication)
was relayed through the hub to the English specialist as the document peer:hi-p5 and quoted in
its reading of the poem.

| Lens | Rate | Round-5 findings confirmed fixed / still open | New findings (blocker / major / minor) |
| --- | --- | --- | --- |
| results-audit | 0.724 | 18 / 1 | 0 / 6 / 3 |
| communication-fidelity | 0.49 | 15 / 0 | 0 / 7 / 6 |
| adversarial-live | 0.8329 | 15 / 0 | 0 / 8 / 6 |

As run for the overseers, the harness counted 46 / 46 functional (the genuine outputs, 6 mutations
each, the peer relay and the 5 syntheses). One genuine receipt carried an error-level finding:
hi-t12, an engine-signed INT-SUBJ-001 on a true sentence that all three overseers judged false.
Seven more genuine or synthesis receipts carried warnings only (en-t11 and en-t12 ES-STR-001 and
INT-REQ-005; INT-SYNTH-012 on five syntheses; the p5 synthesis also an INT-LEDGER-019 that the
overseers judged false). No lens
reached 0.98. The round brought 36 new findings (0 blockers, 21 majors, 15 minors).

What the round-6 overseers found:

- **A false engine-signed error on a genuine answer.** In hi-t12, 'From 1961 the flow slowed to
  roughly fifteen states by 1968, including Tanganyika in 1961, Kenya in 1963 and Botswana in
  1966.' got INT-SUBJ-001: the containment reader took the last date before 'including' as the
  whole outer period. In a dated list only the first item was checked against the cue, so later
  items that contradict it passed with a signed ENTAILED.
- **Arithmetic that was never read.** Figures with a currency sign ('$4.03', '$13 billion', '£600
  million'), the direction word 'devalued', parts of a stated total, part-whole and rate-trend
  relations: none were decided or reported undecided, so no arithmetic of the hi-t11 answer was
  ever checked. A figure of more than 4,300 digits raised ValueError inside the packs; the receipt
  then carried INT-INTERNAL-001 and lost every subject finding of the report.
- **Verdicts shown on encodings that assert nothing.** Translations that define each stated figure
  as 'b <-> (n = k)' but never assert it were accepted, and the engine's COUNTEREXAMPLE, which
  simply sets the figure to another value, was displayed to the router as the verdict on five
  genuine claims.
- **Support cycles.** Every History report with a point and a judgement or link reached the router
  with circular `supporting_claim_ids`, and no branch named a support cycle.
- **Notes and self-reports on the English branch.** en-p5's closing caveat on the peer's labels was
  delivered as the paragraph's material link and its real conclusion as supporting.
  Self-certifications of compliance and of quotation fidelity passed as content on both branches.
  A JSON fragment in a paragraph took prose out of the word count while the parser kept that prose
  as claims.
- **Credit to a colleague.** The credited clause ended at a decimal point, so a correct paraphrase
  of the peer's '5.2 million' raised a false INT-REQ-014 naming '5'. A colleague's date re-paired to
  another event in an unquoted paraphrase crossed silently. A sentence reporting the History
  specialist's view was delivered as the English specialist's own interpretation. A claim id
  already delivered by another agent's report of the task was delivered with no finding.
- **Combinator.** Synthesized claims could change what their sources said (a day-month date among
  them) with only the generic INT-SYNTH-012 that the faithful synthesis carries too, and
  INT-LEDGER-026 read only a one-word exchange between copied words.
- **Coverage and verdicts.** hi-t12's outline item was told it was unaddressed, and four of six
  wordings that answer its verdict item were delivered as evidence.
- **Robustness and cost.** A structured report passed as a JSON mapping without the caller
  repeating its ids still raised out of the hub; the two branches disagreed on an answer that is
  only JSON; large answers took more than 5 s, linearly in the number of formal checks with no cap.
  The English splitter did not cut after a sentence ending in 'I?'.
- **Harness.** The headline counted the genuine hi-t12 receipt with its false error as functional
  with nothing near it saying so, and gave the five displayed COUNTEREXAMPLE verdicts only as a
  count.

What the fix round changed (33 findings reported fixed; commit 23707b9):

- **Chronology.** Containment reads the outer period correctly and checks every item of a dated
  list ('including', 'which included', coordinated objects); intransitive 'followed', event lookup
  across the paragraph and a 'when' clause dated in an aside are read.
- **Arithmetic.** Currency signs and direction words such as 'devalued' are read, and so are parts,
  shares and totals; a figure too large to compare is named undecided ('too large to check'),
  never raised. A transmission's formal checks are capped (`packs.MAX_FORMAL_CHECKS = 500`); the
  statements beyond the cap are named unchecked.
- **Encodings that assert nothing.** The engine adds E110 (unasserted figure) to a COUNTEREXAMPLE
  that only reassigns a figure the problem defines but never asserts; the translator rejects such
  output and the outcome layer displays it as INVALID_FORMALIZATION, never as a verdict.
- **Supports and structure.** Supports follow the stated direction and never cycle, and the core
  pack names any support cycle on every branch (CORE-STR-001, error). The verdict wording is wider,
  and a JSON-only answer has the same outcome at every depth on History.
- **Credit to a colleague.** `credited_spans` and `clause_boundaries` never end a clause at the
  point of a decimal or after an abbreviation or initial; INT-REQ-014 names a date re-paired to
  another event. New INT-REQ-016 (warning): a claim id another agent's report already holds,
  named at delivery. A reported view of the colleague is roled `perspective` (certainty probable,
  with the attribution assumption) through the shared `markdown.is_peer_attribution`.
- **English notes and self-reports.** A note about the answer or about a received report is
  `other`; compliance, sourced-quotation and word-count self-reports are recognised; the splitter
  cuts after '?', '!' and the pronoun 'I'; the body of a prose code fence is kept and counted.
- **Coverage and hub.** An adjective of place meets its place ('African' meets 'Africa'), so
  hi-t12's outline item is covered. A structured report received as a mapping takes its sender and
  report id from its own fields, so nothing raises into the router.
- **The harness.** The results audit found that the headline hid wrong receipts:
  - *Error-carrying genuine receipts are stated under the headline.* summary.md now has a line
    under the headline giving the number of genuine transmissions, peer relays and syntheses, how
    many carry an error-level finding (each named with its codes and claim ids), how many carry
    warnings only, how many of each are counted functional, and that the rate does not judge
    whether a finding is true. results.json carries the same figures as
    `genuine_receipts_with_errors`. The functional definition is unchanged, so no rate moved.
  - *Every displayed verdict other than ENTAILED is named.* Each outcome record now also keeps
    what a verdict without a core rests on: the number of premises of the translated problem, with
    how many are ungrounded or unverified (by the engine's own rule), the conclusion's label, the
    engine's diagnostic codes and the assignment the engine returned (the counterexample, or the
    witness of a CONSISTENT or SATISFIABLE result). A COUNTEREXAMPLE relies on no premise: it holds
    every premise and falsifies the conclusion. Every definitive verdict other than ENTAILED
    displayed on a genuine claim is listed in results.json
    (`displayed_non_entailed_definitive_outcomes`) and in summary.md with its claim id and what it
    rests on. A definitive engine status that the outcome layer withholds (E108 vacuous, E110
    unasserted figure; displayed INVALID_FORMALIZATION) is not listed, because the router is not
    shown it. The line on ENTAILED verdicts that rest only on ungrounded premises now names those
    claims too (`entailed_dependencies.resting_only_on_ungrounded_premises_claims`).

Applied to the records exactly as run for the overseers, the new lines read as follows. r6 has 12
genuine, relay and synthesis records. One carries an error-level finding (hi-t12.json [genuine]:
INT-SUBJ-001 ['h1.5']) and is counted functional, and seven carry warnings only. The displayed
COUNTEREXAMPLE verdicts are hi-p5 h1.5, hi-t11 h1.4 and hi-t12 h1.2, h1.4 and h1.7. r4, whose
summary also gave its verdicts only as a count, displayed eight COUNTEREXAMPLE verdicts on genuine
claims: en-t8 p4-point, hi-p3 h1.6 and h1.7, hi-t7 h1.5 and h1.9, and hi-t8 h1.1, h1.3 and h1.4.
Each holds every premise of its problem and falsifies the conclusion; the eight problems have 32
premises between them, 31 of them ungrounded, and hi-t8 h1.4 ('The turning point was 1930.') has a
problem with no premise at all.

Left open by the round-6 fix round: a dated fact taken as a History paragraph's point by position
is still supported by the paragraph's evidence sentences (making it take no supports would change a
channel test owned elsewhere); the formal-check cap is 500 rather than the suggested 200, because a
channel test pins 500; the reason sentence after hi-t12's verdict is still roled supporting;
CORE-SELF-001 still searches only the old vocabulary, so the new self-reports reach the router as
INT-HANDOFF-006 (and ES-META-001 on English) but not CORE-SELF-001; the History parser's own peer
attribution rule lacks some reporting verbs; synthesized claims are still aligned to their sources
word by word, not clause by clause; HI-STR-001 still fires on genuine hi-t12; the recorded r6 en-p5
translations have no fixture for the now-eligible conclusion p1-s11.

Harness after the fix round, re-run on copies of each round (the recorded round directories were
not written), on the code as it stood during the round-6 fix round:

| Set | Functional before | After | Genuine, relay and synthesis records with an error-level finding (all counted functional unless noted) | Definitive verdicts other than ENTAILED displayed on genuine claims |
| --- | --- | --- | --- | --- |
| r6 | 46 / 46 | 46 / 46 | 0 of 12 (hi-t12's false INT-SUBJ-001 is gone on this code); 8 with warnings only | 0: the five COUNTEREXAMPLEs are now INVALID_FORMALIZATION with E110 (unasserted figure) |
| r5 | 46 / 46 | 46 / 46 | 1 of 12 (hi-p4 synthesis: INT-LEDGER-002) | 0 |
| r4 | 46 / 46 | 46 / 46 | 1 of 12 (en-p3 synthesis: INT-LEDGER-002 on h1.8 and p1-s08) | 8, as listed above |
| r3 | 46 / 46 | 46 / 46 | 2 of 12 (hi-t5 and p2 syntheses) | 0 |
| r2 | 46 / 46 | 46 / 46 | 2 of 12 (hi-t4 and p1 syntheses) | 0 |
| r1 | 30 / 30 | 30 / 30 | 3 of 8 (the en-t2, hi-t1 and hi-t2 syntheses) | 0 |
| r1-adv | 150 / 151 | 150 / 151 | 6 of 23: five INT-REQ-005 request constraints the hostile variants do not meet (four word bounds, one 'no claim carries a source reference'), counted functional, and the empty response's INT-REQ-009, the one record not counted functional | 0 |

## Round 7 (all sixteen specialist agents, four lenses, overseer agents attached)

Round 7 carried 22 specialist answers in 19 hub tasks from sixteen specialist agents across fifteen
IB subjects: English A: Literature (two agents), English A: Language and Literature, History,
Economics, Business Management, Psychology, Geography, Language B: Spanish, Computer Science,
Physics, Chemistry, Biology, Environmental Systems and Societies, Mathematics: Analysis and
Approaches, and Mathematics: Applications and Interpretation. Fourteen of the sixteen agents were
new to the arena. Apart from the two English A courses and History, every subject is parsed by the
generic parser (Psychology, Economics and Business Management with packs of their own). Task types range from analytical paragraphs and essays to
data responses, structured questions, code tracing, worked solutions and marking feedback. Three
tasks were peer groups, each with a recorded combinator synthesis: p7a (Economics to Business
Management), p7b (Physics to Mathematics: Analysis and Approaches) and p7c (History to English A:
Literature). From this round every lens's verdict counts. A fourth lens, translation fidelity,
re-ran every translation of the round through the pipeline and judged it claim by claim. The STEM
build did not join round 7, so four lenses judged it (a fifth counts once the STEM build joins).

| Lens | Rate | Round-6 findings confirmed fixed / still open | New findings (blocker / major / minor) |
| --- | --- | --- | --- |
| results-audit | 0.532 | 8 / 3 | 1 / 14 / 7 |
| communication-fidelity | 0.4246 | 13 / 1 | 1 / 11 / 6 |
| adversarial-live | 0.7477 | 13 / 1 | 1 / 12 / 2 |
| translation-fidelity (new) | 0.6384 | none (first round) | 0 / 8 / 3 |

As run for the overseers, the harness counted 161 transmissions, 148 functional (91.9%). Ten of the
13 failures were one crash, a ValueError on a superscript digit ('³', '²', '¹') in the ledger's
figure reader: the ess-t13, maa-t13 and ph-t13 syntheses, and maa-p7b's genuine answer with its six
mutations. The other three were altered-quotation mutations (lit-t13, mai-t13, sp-t13) that no
finding named: their genuine records already carried CORE-SRC-003, and in mai-t13 the mutation had
altered the prose, not the quotation. No lens reached 0.98. The round
brought 66 new findings (3 blockers, the same crash named by three lenses; 45 majors; 18 minors).

**The overseer agents.** Three overseer agent instances judged 30 blind dossiers (10 each), issued
from a replay of the round. All 30 verdicts passed validation: each was routed by its dossier digest
to the dossier it answers, the signed audit and its key id were checked, the channel was rebuilt,
the dossier re-issued and matched, the reply accepted unchanged by the verdict intake, and the
verdict then assessed. Of 123 agent-scorable faults present (145 auditor labels less 22
infrastructure labels), the agents named 52, every one through a confirmed accusation. By class:
translation_circular 48 of 48, translation_ungrounded 4 of 31, finding_missing 0 of 35,
claim_not_in_response 0 of 4, false_conflict 0 of 3, self_certification_as_content 0 of 2 (macro
recall 0.188). Of 83 accusations, 49 were confirmed (all matching gold faults), 11 refuted by a
deterministic re-run and 23 left unresolved for human review; precision was 49 of 83, and no false
accusation was accepted, so 0 of the 42 clean transfers were falsely accused. All 19 engine
statements in the verdicts agreed with the signed stored results, so the no-contradiction gate and
the false-accusation-rate gate (0.0) passed; the injection gate was not measured, because no gold
dossier carries the injection flag. Two dossiers contained page text addressed to AI reviewers; the
agents treated it as content and did not follow it. The 15 functional arena injections were already
named by the channel's receipts and the agents did not accuse them again. Three lenses found that
the validation was itself wrong in one place: 9 of the 11 refuted 'false accusations' were correct
false_conflict accusations, refuted because the deterministic re-run repeated the conflation the
agents had named (see below). The dossiers were also replayed on the overseer build's older channel
and arena code (143 transmissions, 135 functional), not on the main code this round's results.json
reports.

What the round-7 overseers found:

- **A crash on scientific notation.** A stand-alone superscript, subscript or circled digit ('min⁻¹',
  'mg dm⁻³', '10³', '(1/2)⁴', 'P₁', '①'), which every STEM specialist writes, raised ValueError out of
  `RouterHub.receive` and `TranslatorChannel.relay`: `str.isdigit()` is true for '³' but `int()`
  rejects it.
- **False error-level conflicts.** Correct specialists were charged INT-CONFLICT-001 because the
  translator gave one symbol name to different quantities (targets 67, 20 and 9; lists of 10 and
  1,000 items; the marks of part (a) and part (c)), although INT-GLOSSARY-005 on the same receipt
  said the glosses differ. INT-REQ-007 ('rests on premises that contradict each other') was an
  error on AMBIGUOUS_TRANSLATION claims whose premises conflict only under the literal reading of a
  rounded figure.
- **The generic branch distorted structure.** Two generic-branch reports of one peer group got the
  same claim ids (20 of ec-p7a's 21 ids reappeared in bm-p7a), so the router held two claims under
  one id. Part and mark labels ('(a) [2]') became the material point of every part while the
  computed answers were supporting; 'Note:' blocks became material points of extra body paragraphs.
- **Request fidelity.** A word limit stated 'plus working' was applied to the working and the
  diagram, giving false INT-REQ-005 errors on five genuine receipts; multi-part questions were
  lumped into one item and some parts dropped; numbered answers in Spanish were told an item was
  unaddressed.
- **Arithmetic left silent.** Worked equations on the Economics, Business, sciences and mathematics
  answers ('Break-even quantity = $6,000 ÷ $2.00 = 4,000 loaves') were neither decided nor reported
  undecided, and a stated duration was decided only in one wording, so the genuine hi-p7c error
  ('more than twelve years' from 1949 to 1961) crossed silently.
- **Quotations and credit.** With texts supplied, an altered or invented quotation of a supplied text
  in a sentence naming no text was only the CORE-SRC-003 'cannot be verified' warning, never
  INT-REQ-003. Peer attribution was decided per sentence: in lit-p7c, two quotations of the poem
  after a colon were credited to the History specialist, giving four errors on a correct paragraph.
  bm-p7a was told it misreported the Economics specialist's figures, which were its own
  calculations on the lines after the quotation. Words quoted from the request were called
  unverifiable quotations.
- **Combinator.** The figure-pairing reader raised false 'exchanged' and 'dated' INT-LEDGER-023
  errors on faithful syntheses of worked answers (arrows, equation chains, a figure on one line and
  its year on the next) and missed a real re-pairing; numbers in other languages ('doce') were not
  read; INT-LEDGER-026 missed a reversed thesis in a merged claim and warned on faithful rewordings;
  a change of quotation marks alone was called an altered quotation.
- **Verdicts that say nothing.** A claim translated as one atom with no premises was displayed as
  COUNTEREXAMPLE (ec-t13 g5.3). In 14 translations the premises restated the conclusion, so
  ENTAILED proved nothing.
- **Translation fidelity (new lens).** 143 of the 224 translations judged were faithful. The largest
  single cause of the 81 unfaithful ones (30) was a rounded figure encoded as an exact equality.
  Others: one symbol name reused for different quantities; the claim's own stated reason or reported
  text fact left out; in 12 translations a support link the specialist did not make presented as the
  specialist's; grounding kinds that misstate what a verdict rests on (the specialist's own figure
  grounded as `arithmetic_fact`); 21 claims whose only numerals are mark annotations or part numbers
  sent as quantitative claims.
- **Overseer validation and the harness.** The validation of the agents' verdicts refuted correct
  false_conflict accusations and mis-measured the translation fault classes; the dossiers came from
  older code. The harness silently dropped the p7b group synthesis when maa-p7b crashed (161
  transmissions instead of 162), mutated the prose instead of the quotation in mai-t13, and charged
  an INT-LEDGER-004 artefact to the sp-t13 synthesis.

What the fix round changed (owner-partitioned fixers, regression tests beside each change; 40
findings reported fixed; commit dc77853):

- **The crash.** Every figure reader in the ledger and the cross-agent check tests digits with
  `isdecimal()` on the first character, never `isdigit()` with `int()`, and superscript and
  subscript marks are folded before figures are read (`ledger.fold_exponent_marks`). Every content
  check of `respond` and `relay` runs guarded: a failure is INT-INTERNAL-001 naming the check, never
  an exception.
- **Conflicts and premises.** `split_by_gloss` renames a symbol apart where claims gloss it as
  different quantities; a contradiction that exists only when such a symbol is pooled is the
  INT-CONFLICT-004 warning, charged to no specialist and demanding no disclosure. INT-REQ-007 is an
  error only for a TRANSLATED outcome and a warning, naming the assumed reading, under
  AMBIGUOUS_TRANSLATION.
- **Verdicts that say nothing.** E108 also covers a COUNTEREXAMPLE over zero premises; new E111
  (unencoded reason: the conclusion fails only through figures no premise states) and E112
  (circular: ENTAILED from premises that restate the conclusion from the writer's own assertions).
  Each is displayed as INVALID_FORMALIZATION. The translation pipeline rejects circular encodings and
  exact equalities to rounded figures ('stated precision', a figure stated to n places read as half
  a unit of its last place), and the prompt lists all ten grounding kinds with `arithmetic_fact`
  narrowed to task figures and figures computed from them. Eligibility counts figures on the
  figure text, so mark annotations and part labels are not figures.
- **The generic branch.** Claim ids are qualified by the agent ('g4.2@economics-specialist');
  answers are read line by line, with an equation chain as one claim; part labels and mark
  annotations are no claims; notes, questions and headings are `other`; each part's answer is a
  material point; supports follow the stated direction.
- **Request fidelity.** 'plus working', 'plus working and your diagram' and 'excluding working' set
  equation lines, tables, working blocks and diagram descriptions aside from the word count; a
  'Note:' block is out of word and paragraph bounds; the request is split into one item per
  labelled part.
- **Quotations and credit.** INT-REQ-003 (error) now refutes an uncredited quotation when a supplied
  text holds all its words but one or two (named as 'an altered quotation') or when its sentence
  credits it by kind to the text under analysis. Each quotation is credited through its own clause
  (`quotation_credit`): a named text is a misattribution only when its mention governs that
  quotation, a credited clause ends at a line break, and 'supplies', 'provides', 'offers' and
  'frames' are crediting verbs. The core pack drops quotations located in the request and reports a
  short uncredited quotation with no text supplied.
- **Arithmetic and chronology.** Worked equations that a branch does not decide are named undecided
  (CORE-QNT-001, 'states worked arithmetic'), never passed silently; stated durations are read across
  sentences, which now names the genuine hi-p7c error on h1.1.
- **Ledger.** Worked answers are read as equation clauses (operands pair with nothing; each result
  pairs with its own name), arrows end a clause and LaTeX markup is read; INT-LEDGER-026 aligns
  sentence by sentence; quotation marks inside a quotation are set aside.
- **The harness** (`scripts/arena/run_arena.py`, regression tests in
  `scripts/arena/test_arena_rules.py`):
  - *Every group has one synthesis record, whatever happened to its members.* In a round that
    carries syntheses, the group's synthesis is made after its last member whatever happened to the
    members (a crash, a rejection, a peer report never relayed). The synthesis of the delivered
    members is relayed and its receipt kept. A member that was not delivered is named
    (`members_not_delivered`) and makes the record a failure, and a group with no delivered member
    gets a failed record saying so. A crash in the router's forward to a peer, or in a mutation's
    peer set-up, is recorded on its record and no longer ends the round.
  - *Evidence references a synthesized claim reproduces are kept.* The sp-t13 synthesis was charged
    INT-LEDGER-004 only because the syntheses format had no field for references, although s2
    quotes both of g4.1's excerpts word for word. A synthesized claim may now carry
    `evidence_refs`, which are passed on as written; a claim without them keeps the references of
    its cited material source claims whose excerpts its text reproduces word for word
    (`evidence_refs_copied`). A claim that drops or rewords the evidence is still charged
    INT-LEDGER-004. With both of g4.1's references kept, the ledger raises a false INT-LEDGER-020
    warning, because it keys references by (document, locator) alone and both quotations have no
    locator; this was handed to the integrity owner.
  - *The altered quotation misquotes a supplied text, at a word, inside its own span.* The
    quotation altered is the first one found verbatim in a supplied text (a relayed peer report
    included), else the first quotation, and it is changed inside its quoted span at an alphabetic
    word: the middle word when it is a word, else the nearest word ('boxly.', 'streamly.' and
    'countsly' instead of 'I fill a box.ly', 'stream.ly' and '20ly'). Before, the mutation could
    also pick a quotation of the request. On r1 to r6 only the five quotations whose middle word
    carried punctuation or was a mark changed (r1-adv hi-t1, r5 en-p4, en-t9 and en-t10, r6
    en-t12); every other altered quotation is as before.
  - *A task with a supplied text must refute a quotation mutation.* With a supplied text of the
    task's own, invented and altered quotations are expected as INT-REQ-003 only. When the only
    supplied text is a relayed peer report, either INT-REQ-003 or CORE-SRC-003 is accepted; with no
    supplied text, CORE-SRC-003 is expected.
  - *Encodings given no verdict are counted* in summary.md (`withheld_verdicts`): E108, E110, E111,
    E112 and 'stated precision', with their claim ids.
  - *Fixtures that match no delivered claim are reported*
    (`translation_fixtures_matching_no_delivered_claim`).

Because the generic parser now qualifies ids by agent and reads line by line, the recorded r7
translation fixtures and syntheses, which cite the ids of the earlier parse ('g4.1'), mostly no
longer match. A re-run of r7 serves 24 of the recorded fixtures (200 match no delivered claim id,
all named in summary.md), and the generic-branch syntheses carry INT-LEDGER-001 and INT-LEDGER-002
for the old ids. The fixtures carry no `claim_text_sha256` and the earlier claim texts are not
recorded, so the harness cannot re-key them safely: keying by the bare id would serve a fixture to
another sentence. A copy of r7 with fixtures and cited ids re-keyed by claim text against the
earlier parse gives 162 / 162, 159 translation outcomes and no unserved fixture; on that copy
sp-t13's synthesis carries no INT-LEDGER-004, and 17 genuine claims get no verdict (9 circular, 8
stated precision). Rounds from 8 on should record `claim_text_sha256` for every fixture
(`list_claims.py --json` prints it).

Harness after the fix round, re-run on copies of each round directory, first with the harness as it
was and then with the fix, on the code as it stood during the round-7 fix round:

| Set | Functional, harness before | After | Synthesis records | Genuine claims given no verdict (after) |
| --- | --- | --- | --- | --- |
| r7 | 161 / 162 (recorded: 148 / 161) | 162 / 162 | 19 of 19 groups | 6 (E112); 200 fixtures unserved (ids changed) |
| r6 | 46 / 46 | 46 / 46 | 5 | 10 (8 E110, 2 E112) |
| r5 | 46 / 46 | 46 / 46 | 5 | 3 (E112) |
| r4 | 46 / 46 | 46 / 46 | 5 | 1 (E108, hi-t8 h1.4) |
| r3 | 46 / 46 | 46 / 46 | 5 | 6 (E112) |
| r2 | 46 / 46 | 46 / 46 | 5 | 3 (E112) |
| r1 | 30 / 30 | 30 / 30 | 4 | 1 (E112) |
| r1-adv | 150 / 151 | 150 / 151 | none (no syntheses) | 0; the empty response's REJECTED genuine record remains the one failure |

On r7, with the harness before the fix and the same code, the one failure was mai-t13's altered
quotation, which had been altered in the prose. With the fix, 40 of the 52 quotation-mutation records
across r7 are held to INT-REQ-003 alone, and every one is named by it.

## Final verification after the round-7 fix round

On the code after the round-7 fix round, the suite gives 1855 passed, 12 deselected (the
stress-marked tests), with no failing test. The harness, re-run on every recorded round:

| Round | Functional | Genuine, relay and synthesis records with an error-level finding (all counted functional unless noted) |
| --- | --- | --- |
| r1 | 30 / 30 | 3 of 8, all syntheses: en-t2 (INT-LEDGER-025), hi-t1 and hi-t2 (INT-LEDGER-003) |
| r1-adv | 150 / 151 | 6 of 23: INT-REQ-005 on five hostile variants (en-t1-long-paragraph, en-t1-wrong-register, en-t2-only-quotation, hi-t1-530-sentences, hi-t2-long-bullets-nopunct), and the empty response's INT-REQ-009, the one record not counted functional |
| r2 | 46 / 46 | 2 of 12, syntheses: hi-t4 (INT-LEDGER-003), en-p1 (INT-LEDGER-002, INT-LEDGER-003) |
| r3 | 46 / 46 | 2 of 12, syntheses: hi-t5 (INT-LEDGER-002), hi-p2 (INT-LEDGER-003) |
| r4 | 46 / 46 | 1 of 12: the en-p3 synthesis (INT-LEDGER-002) |
| r5 | 46 / 46 | 2 of 12: hi-p4 genuine (INT-REQ-003) and the hi-p4 synthesis (INT-LEDGER-002) |
| r6 | 46 / 46 | 0 of 12 |
| r7 | 162 / 162 | 18 of 44: 15 recorded syntheses cite claim ids the current parse no longer issues (INT-LEDGER-001, INT-LEDGER-002; lit-t13's also INT-LEDGER-003 and INT-LEDGER-023), the lit-p7c synthesis carries INT-LEDGER-003, ch-t13's genuine answer INT-REQ-005 (439 words measured against a 540-word minimum), and hi-p7c's genuine answer INT-SUBJ-001 on h1.1 |

Three of these deserve a word. The hi-p7c INT-SUBJ-001 is the duration error the round-7 results
audit named in the genuine answer, now decided. The r5 hi-p4 genuine INT-REQ-003 is new on this
code and reads as a false error: it calls Hardy's 'quaint and curious war' an altered quotation of
the request because the request holds two of its four words ('and', 'war'); the words are the
poem's, which the History specialist was not supplied, so before the round-7 rule it was the
CORE-SRC-003 'cannot be verified' warning. No overseer has judged it yet. The r7 synthesis errors
are artefacts of the recorded syntheses citing the earlier parse's ids, not judgements of the
combinator. Translation outcomes on the genuine pass (provider-dependent, fixtures only): r4
displays six COUNTEREXAMPLE verdicts on genuine claims (en-t8 p4-point, hi-p3 h1.6, hi-t7 h1.5 and
h1.9, hi-t8 h1.1 and h1.3) and withholds one (hi-t8 h1.4, E108); no other round displays a
definitive verdict other than ENTAILED. Genuine claims given no verdict: r1 1, r2 3, r3 6, r5 3 and
r7 6 (all E112, circular), r6 10 (8 E110, 2 E112).

## Replays after the fixes of the external review of 12 October 2026

The nine findings of the external review were fixed in three parts (engine; translation; measures and timing) and
integrated into one tree on the development branch after the STEM merge: engine 0.4.0, policy 2026.10-v4, translator
0.4.0, prompts `translate_v2` and `review_v2`. An independent verification then found finding 6 not closed (below),
and it was repaired at its cause on the same tree; a second independent verification found findings 2 and 6 closed
only for their literal cases, and both were repaired again at their cause (below); a third found finding 6 closed only
for the claim and its supporting claims and a regression in the grounding of rounded givens (finding 1 with finding
9), and both were repaired at their cause (below); a fourth found finding 1 open in a cue-less wording of the reviewer's
probe, and it was repaired at its cause (below). On the four times repaired tree the default suite gives 5264 passed, 45
deselected (the stress-marked tests), 4 xfailed, and the harness rule tests 28 passed. The harness, re-run once on fresh
copies of every recorded round:

| Round | Transport | Fixture coverage | Claims: extracted / eligible / attempted / completed / approved | Approved resting on an unresolved dependency | Release permitted | Given no verdict (by rule) | Advisory W110 / W111 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| r1 | 30 / 30 | 16 of 17 | 71 / 21 / 16 / 4 / 4 | 4 | 0 | 1 (E112) | 0 / 0 |
| r1-adv | 150 / 151 (the empty answer stays REJECTED) | 1 of 2 | 911 / 644 / 1 / 0 / 0 | 0 | 0 | 0 | 0 / 0 |
| r2 | 46 / 46 | 22 of 24 | 120 / 28 / 22 / 2 / 2 | 2 | 0 | 3 (E112) | 0 / 0 |
| r3 | 46 / 46 | 24 of 27 | 87 / 27 / 24 / 7 / 7 | 7 | 0 | 6 (E112) | 0 / 0 |
| r4 | 46 / 46 | 25 of 27 | 100 / 27 / 25 / 8 / 2 | 2 | 0 | 1 (E108) | 0 / 0 |
| r5 | 46 / 46 | 17 of 20 | 90 / 23 / 17 / 6 / 6 | 6 | 0 | 3 (E112) | 0 / 0 |
| r6 | 46 / 46 | 27 of 28 | 93 / 28 / 27 / 15 / 15 | 15 | 0 | 10 (8 E110, 2 E112) | 0 / 0 |
| r7 | 177 / 177 | 22 of 224 (200 claim ids no longer delivered) | 475 / 260 / 22 / 6 / 6 | 6 | 0 | 6 (E112) | 0 / 0 |

Compared record by record with a replay of the code before the fixes (the STEM merge, the same recorded rounds), every
receipt status, functional flag, finding code, displayed status, engine status and engine diagnostic is the same on every
round. The only differences are in the dependency lists: on r5 the hi-p4 h1.3 outcome (in each of its 7 records) and on r7
the lit-t13 p1-point outcome (in each of its 6 records) now list one more unverified dependency, a premise of a
task-authority kind that no check validated, which the engine no longer exempts. The r6 E110 verdicts are still withheld,
now on source-linked evidence: the answers' own sentences assert the figures the encodings only define
(`translate.coverage`), so the engine's E110 rests on a sentence, not on the formula's shape. No recorded encoding leaves
open a figure that no source asserts, so no advisory W110 or W111 appears on these rounds. Compared record by record
with the replay of the previous repaired tree (finding 6 repaired once), every receipt status, functional flag, finding
code, displayed status, engine status, engine diagnostic, dependency list and translation status is the same on every
round: no recorded translation rests on a relation that its figures alone had established, and no recorded source
asserts a figure in a construction the positive reader no longer recognises. The replay of the thrice-repaired tree is
identical, field by field (timings, identifiers and signatures aside), to the replay of the twice-repaired tree on every
round, so none of the recorded material turns on what the third repair changed (the sources E111 reads, sentence ends
before a lower-case symbol, questions opened by a given, frames that name the task, figures negated in their own
predicate, the intervals rounded figures state). The replay of the four times repaired tree is in turn identical, field
by field, to the replay of the thrice-repaired tree on every round: no recorded translation turns on what the fourth
repair changed (when a figure is the result of a written calculation, and which figure an approximation cue governs).

Every approval on these rounds rests on at least one unresolved dependency, and no claim's release assessment permits
release: a replay calls no fidelity reviewer, and release also needs established premises and the engine's release
check. The formal statuses are reported as before; permission to release is a separate record. The harness keeps its
injected verifier at the two-argument signature, so a replay translates on the recorded path (task-authority premises
are validated against the supplied texts, not against the router's question). Passing the task record is a methodology
change for a new round.

The reviewer's reproduction scripts, re-run on copies, now show: the exact claim keeps its COUNTEREXAMPLE (x = 1/3) with
no retry, the contradictory exact facts stay INCONSISTENT_PREMISES, and the old widening repair no longer earns ENTAILED;
the invented 160 km is a failed grounding check and an ungrounded dependency (the formal ENTAILED is kept apart from
release, which is refused, and the relation `speed = d / 8`, which the supplied text does not state, is listed as an
unverified dependency beside it); a model-chosen arithmetic_fact, task_setting or rubric_rule is an unverified dependency
with cores on and off; the tautology with cores off carries E108; the reviewer request carries the task, the supporting claim,
the supplied text, the identities and the premise-to-source mapping; the baseline signed result still verifies but is
displayed INTERNAL_ERROR and fails the binding check (INT-STALE-005); the definition and the arbitrary variable keep
their counterexamples with W110 and W111; the mixed reference list is not verified (one reference refuted); `x*x = 4`
binds different digests under default and permissive limits; `20%` verifies as `0.2` and as `1/5`. The acceptance
criteria of the review's section 3, with negative controls, pass 197 of 197: 22 for the fourth verification's cases (the
cue-less conditional in the five listed wordings, the comma form and three more of the class, each with the faithful exact
encoding and the widened one, under a review that calls both faithful; an operator after a variable; four controls: the
exactness cue, a calculation written right before the '=', a genuinely rounded claim at its stated tolerance), and the
175 of the third repair's measurement: 62 for the third verification's cases (40
for finding 6: E111 and E110 in every source, with the non-asserting phrasings and a record figure about nothing the
encoding names as negative controls; 22 for finding 1 with 9: the seven rounding phrasings transcribed exactly and at
their stated tolerance, five intervals that are not the stated tolerance, the stated-precision retry and a rounded
percentage), 6 for the negation found while measuring it, and the 107 of the second repair's measurement, made of the 55 of the first repair's measurement,
with finding 2's "the authentic 120 must still support 15" now measured under the whole-content rule (formal ENTAILED,
the distance established by the text, the unstated relation an unverified dependency that blocks release; with the
relation stated by the text every premise is established and release follows the faithful, current review; with no
review it is not released) and finding 4's staleness check measured where release is permitted before the change, plus
50 for the second verification's cases (16 for finding 2, 34 for finding 6). No live provider was called; translation
fidelity has not been re-measured.

**Finding 6, repaired after independent verification.** The first fix kept the reviewer's two literal examples
("Define b iff n=17", "y is an arbitrary integer") but decided whether a source asserts a figure by a list of
definitional keywords over the whole sentence and, for E111, by the presence of any figure the encoding omits. Natural
paraphrases of the same faithful questions were therefore withheld as mistranslations: "If n equals 17, b holds; so b
necessarily holds", "When n equals 17, b holds", "Is n equal to 17?", "n could be 17, and b holds just when n is 17", "b
holds exactly when n equals 17", and, for E111, "Given x = 5, x < y for any integer y; I checked 3 values" and "... for
each of the 2 integers y we pick". Worse, the retry feedback then told the translator that the source asserts 17, and a
retry that added `n = 17` was accepted and displayed ENTAILED for a non sequitur. The repair (`translate.assertion`)
reads the source's grammar clause by clause: a figure is evidence only when its clause asserts it (no question,
instruction, condition, conditional "when", supposition, example, definition, possibility, obligation, intention, hedge,
attribution, negation, quantification or disjunction governs it, each with a stated scope), when what it states
establishes the comparison the encoding defines ("more than 17" establishes no `n = 17`), and when it is about the
encoding's symbols (a figure that counts something else is not). The retry an E110 asks for may add only what the
source evidence states; any other added premise makes the translation AMBIGUOUS_TRANSLATION (`retry_added_premise`).
On copies, the verifier's own probes now keep every one of those counterexamples with W110 or W111 and one provider
call, and the source-asserted controls are still E110/E111; three paraphrase batteries (139 cases: 114 faithful
questions, 25 sources that do assert the figure, in mathematical and History wording) give the expected outcome in
every case. The recorded rounds replay identically, record by record, to the first integrated tree: the r6 answers'
eight E110 verdicts stay withheld, since those answers assert their figures ("in 1960, when seventeen African states
became independent" relates a fact), and no recorded encoding leaves open a figure a source does not assert. That
reader was lexical in the unsafe direction: a construction it did not know read as asserting. The second verification
found exactly that (below), and the reader now asserts only what it positively recognises.

**Findings 2 and 6, repaired again after the second verification.** The second independent verification found both
fixed only for their literal cases. Finding 2: the authority check (`numeric_in_task`) and the excerpt check
(`figures_in_excerpt`) verified a premise once its numerals occurred in a record, never its relation, so an invented
formula `speed = d * 8` beside "A car travels 120 km in 8 hours" counted as established under `arithmetic_fact`,
`task_setting` or `rubric_rule` (hidden from both dependency lists, release permitted with a faithful review) and was
listed only under `general_knowledge` or `assumption`: the model's label still decided. Finding 6: seven of the
verifier's 32 non-asserting phrasings still read as asserting n = 17 ("Students often guess that n is 17, but this is
not given.", "Claim to test: n is 17.", "In some cases n is 17.", "Hypothesis: n is 17.", "According to rumour, n is
17.", "n = 17 ⇒ b.", "b ⟺ n = 17."), each withholding a valid counterexample (E110), because the reader read any
construction it did not know as asserting.

Both were repaired at the cause, for the whole class. A check confers task or source authority only on a premise's
whole content (`translate.relations`): an assignment (each symbol compared with a literal) by records that state each
figure so that it establishes the comparison ("more than 17" establishes no `n = 17`), and any other numeric content,
a relation, only by a record that states the same formula as a given (`relation_in_source`; a closed formula reader,
nothing evaluated; a formula in a question, a claim to prove or a condition is no given). Figures in a record never
verify a relation, and a located excerpt holding them does not either: an unstated relation is an unverified
dependency that blocks release whatever its label, and the outcome lists it under "Unverified relations". The
assertion reader asserts a figure only where it positively recognises the clause as the writer's own statement;
anything it does not recognise keeps the counterexample with the advisory W110/W111. On copies, the verifier's probes
now give: the invented `speed = d * 8` is an unverified dependency under each trusted kind and an ungrounded one under
`general_knowledge` and `assumption`, release refused in all five; of its finding-6 cases, all 38 non-asserting ones
(the 32 phrasings in the task, 6 of them also as a supporting claim) keep the counterexample with W110 and one provider
call, all 12 asserting ones are still withheld (E110), and its E111 pairs give W111 (4) and E111 (3). A battery of 280
phrasings (hedges, hypotheses, reported speech, claims to test, quantified and symbolic conditionals and
biconditionals, and asserting controls) reads every one as expected, and so do the first repair's three batteries. The
measurement of this repair found two faults in it, fixed and tested before the final measurement: two references to one
document kept only the last located span (a premise `d = 120` cited as "Distance 120 km" and "8 hours" was refuted in
one order), and a statement through a raising verb ("n turned out to be 17") or a factive frame at a line break of the
frame list ("We note that") read as unrecognised (the conservative error). The reader's remaining limits are stated in
`translate/assertion.py`: a genuine statement in a construction it does not recognise is read as unasserted, and an
unknown verb of report or opinion before a bare clause ("Pupils opine growth was 17") is the one shape it can still
misread as asserted.

**Findings 6 and 1/9, repaired after the third verification.** The third independent verification found finding 6
closed only for the claim and its supporting claims, and a regression of the precision repair. Finding 6: the coverage
step read the evidence for E111 (a figure asserted about a conclusion symbol no premise mentions) only from the claim and
its supporting claims, although the pipeline's own account named the supplied texts and the task record too, so "Here x
= 5 and y = 9." withheld the counterexample to an encoding that omits y = 9 as a supporting claim (E111) but displayed
that counterexample as the verdict (W111) as a supplied text or as the task record, the most authoritative sources; and
a sentence that opens with a lower-case variable was not split from the sentence before it, so the instruction of
"Define b to hold iff n equals 17. n = 17." and "Define b. n = 17." governed the second 17 (W110 and the counterexample,
where the source asserts n = 17). Finding 1/9: "0.33 to 2" in the supplied fact "x is 0.33 to 2 decimal places." was
read as one end of a range, so its exact transcription x = 0.33 failed grounding (it had grounded before the precision
repair), and the interval [0.325, 0.335) that the precision step demands when the rounding matters always failed the
excerpt check, so no faithful encoding of a rounded given could ground.

Both were repaired at the cause, for the whole class. The coverage step reads every source for both shapes
(`translate.coverage.assess_unconstrained`); a figure of a supplied text or of the task is evidence about a free symbol
only in a clause about it (it names the symbol, counts what describes it, or shares the words that describe it), while
the answer's own figures link as before. A full stop before a lower-case symbol that opens a statement ends the sentence,
as one before a capital does (`translate.quantities`), never after an abbreviation ("e.g.", "i.e.") or before a
lower-case word that continues the sentence ("Suppose b holds. then n = 17."). In the same class, a question opened by a
clause that presents a fact ("Given x = 5 and y = 9, is x < y?", "Given n = 17, does b hold?") no longer governs that
clause, and a frame that names the task ("In this problem n is 17.") presents its given, while a hypothetical frame ("In
this scenario") stays unrecognised. The numeral of a precision cue is no end of a range, and a figure stated as rounded
establishes the ends of the interval it states (`translate.quantities.stated_intervals`, one recorded derivation; a
symbol bounded on both sides takes both ends from one figure), never a wider, narrower or shifted interval, while an
exact or given figure states no interval. Measuring the repair found one more fault, present before it: the excerpt
check read a negation only where the figure stands ("≠ 0.33"), so a record saying "x is not 0.33." established x = 0.33;
a negation in the figure's own predicate now establishes nothing, while a bound phrase ("not more than") keeps its
reading.

On copies, the third verification's probes now give: "Here x = 5 and y = 9." withholds the counterexample (E111) as a
supporting claim, a supplied text and the task record alike; "Define b to hold iff n equals 17. n = 17." and "Define b.
n = 17." withhold it (E110, fed back once with the asserting clause) in every source; the non-asserting phrasings ("Let
x = 5 and y = 9. Show that x < y.", the reviewer's arbitrary y, a possibility, a hypothesis) keep W110/W111 and the
counterexample; each of the verifier's seven rounding phrasings grounds both the exact transcription and the interval at
the stated tolerance, with the claim ENTAILED and its release permitted under a faithful review; and the case where the
rounding decides the claim is rejected exactly (stated precision), its retry at the stated interval grounds, and its
counterexample is the verdict, with no failed grounding check. Reading every figure of a long record stays linear
(100,000 characters under the suite's 2 s bound, for E111 and for the tolerance derivation), and the first repair's three
paraphrase batteries and the second repair's 280-phrasing battery still give the expected outcome in every case.

**Finding 1, repaired after the fourth verification.** The fourth independent verification found the reviewer's
reproduction succeeding again with "exactly" left out. In the cue-less conditional "If x = 1/3 then x = 0.33." (and "x =
1/3 implies x = 0.33.", "When x = 1/3 it follows that x = 0.33.", "Given x = 1/3 we get x = 0.33.", "Claim: if x = 1/3 then
x = 0.33, which is false.") the figure 0.33 was read as the rounded result of the written calculation "1/3 then x =
0.33": the reader took the left side of an '=' for a calculation whenever an operator stood anywhere in it, and dropped
the words after a numeral ("then x") as its unit. The faithful exact encoding, whose counterexample x = 1/3 is valid,
was rejected for its stated precision and the translator was told to widen 0.33; the widened retry was accepted as
ENTAILED, recorded as an unchanged semantic repair and released under a review that called it faithful.

Repaired at the cause, for the whole class (`translate.quantities`). A figure is the result of a written calculation
only when the calculation ENDS at its '=' and the figure ends the expression: the words right before the sign belong to
the calculation only as the unit of its last operand (one the STEM unit table, a currency or scale word or an everyday
measure reads; a count noun only inside the calculation); the calculation starts with an operand (an operator after a
variable, a sign glued to a variable, a numeral glued to an identifier and a bracket written against a symbol, "f(2)",
continue an expression that holds a term that is no numeral); and a figure followed by an operator, or written against
a bracket, a root, a letter or a power, is an operand of a further expression ("= 3 − 1", "= 5(2 × 3)", "= 2√3"). The sign
in each listed phrasing therefore equates 0.33 with the variable x: the figure is unstated, and an undecorated decimal
whose two readings disagree is AMBIGUOUS_TRANSLATION, after one provider call, never rejected for precision, never
ENTAILED and never released. In the same class an approximation cue, a word or a sign, governs only the figure it is
written against ("think about it", "almost certain", "about 2 people think that ..." and "x ≈ 1/3 so x = 0.33" state
nothing about 0.33; "without approximation" states exactness), where before one cue governed every figure of its clause.
The closed reader also reads calculations it used to miss or misread: LaTeX (`\frac`, `\times`, `\text{}` units),
exponents, vulgar fractions, per cent words, units joined by "per", the unit of a bracketed operand; a function value
inside a calculation is read by the convention, never computed with the function dropped (as "ln 2 / 8.0" was, as 2 / 8.0).

On copies, the fourth verification's probes now give: each listed phrasing, and the comma form it was compared with,
AMBIGUOUS_TRANSLATION after one provider call with the faithful exact encoding (its readings, COUNTEREXAMPLE as written and
ENTAILED to half a unit of the last place, both recorded), release refused, no repair recorded; the widened encoding served
first is AMBIGUOUS_TRANSLATION as well, never displayed ENTAILED; `written_calculation_value(' 1/3 then x ')` and `(' 1/3
then b ')` are None, while `(' 1/3 ')` is still 1/3. Its other probes (findings 2 to 9) and the three earlier
verifications' probes give the same output as on the thrice-repaired tree, identifiers aside, and so do the earlier
repairs' batteries; a battery of 63 phrasings of the class (connectives, arrows, symbols, identifiers, an operator after a
variable, a function symbol, approximation words and signs that govern another word or figure, "without approximation")
with its controls gives the expected outcome in every case. Read over every equation-bearing string of the recorded rounds
and of the test data (3,483 texts, 17,398 figures), the repair moves a reading only in two directions: from a misapplied
rounding (a cue that governs another figure, or a "calculation" whose left side ends in a variable, a symbol, an equation,
a unit conversion or a figure that starts the next expression) to unstated or to what the calculation gives, and from
unstated to the reading of a genuine written calculation the old test missed (LaTeX, exponents, units, scale words). No
reading becomes rounded by a cue it did not have.

## Fixes after the end-to-end simulation of 16 October 2026: the channel and the service

The end-to-end simulation of the website-to-backend flow (all sixteen specialists on the cheapest tier, a frozen copy
of the integrated tree) found two faults on the channel and service side; both reproduced on 22d6a5b and are fixed at
the cause (regression tests: `tests/README.md`).

- **The combinator's synthesis (bug 7).** All 14 group syntheses of the simulation's round crashed in the harness with
  a pydantic ValidationError: the combinator had written a description of each edit in `transformation` ("Verdict (s1.1)
  and reason (s1.2) joined ...; figures verbatim.") instead of one of the documented values, and `run_arena.py` built
  the contract models itself, so the hub never saw the syntheses. The harness now relays each synthesis as the JSON the
  router receives, and the hub's contract validation decides it: such a synthesis is REJECTED with INT-REQ-009 and the
  new INT-SYNTH-014, which names every claim whose transformation (or certainty, materiality, ledger transformation,
  conflict status) is outside the closed vocabulary. The same fault had a second path: a synthesis object built around
  validation (`model_copy`) with a free-text transformation was delivered, its value-specific ledger rules skipped; the
  channel now re-validates synthesis objects as it does reports. The contract keeps its closed set
  (`integrity.contracts.TRANSFORMATION_MEANINGS`), on the evidence of the recorded rounds: the combinator agents of r1
  to r7, told the values, used one of them in all 202 synthesized claims, and the simulation's combinator, whose
  instructions named the field without its values, wrote free text in all 62. `list_claims.py --json`, which the
  combinator runs for every report, now prints the synthesis format with the values and their meanings from the
  contract (`scripts/arena/README.md`, "Synthesis format").
- **The engine policy over HTTP (bug 8).** `POST /v1/verify` always decided under the default limits, so 8 of the
  simulation's 301 genuine-pass engine problems decided differently over HTTP than in the pipeline: seven STEM checks the
  channel ran under `nonlinear` (UNSUPPORTED, E201) and one cross-agent joint check (INVALID_FORMALIZATION, E300 to
  E302). A request (and `epinoic-logic verify --policy`) now names `linear`, `nonlinear` or `joint`, never limits of its
  own; the service applies the name as the in-process caller does, and all eight decide as in the pipeline, each with
  the binding the same payload has in process. Unknown names are refused before anything runs; authentication and the
  rate, size and concurrency limits are unchanged.

Replays on copies, record by record against the harness and code of 22d6a5b (findings and messages compared with ids
masked): r1 30/30, r1-adv 150/151, r2 to r6 46/46 and r7 177/177, every record identical. On a copy of the simulation's
round, the 120 records other than the syntheses are identical, and the 14 synthesis records, which held only the
exception, are REJECTED receipts naming INT-REQ-009 and INT-SYNTH-014 with every claim; they stay failures (genuine
traffic that was not delivered), so transport is 114 of 134 before and after (the six other failures are injected
faults not named, the simulation's bugs 1 to 6, which this fix does not address). With the transformations relabelled
by a fixed rule (one source:
`paraphrased`, several: `merged`; a reconstruction, not what the combinator wrote), the same 14 syntheses are
delivered and decided, transport 128 of 134, so nothing else on the synthesis path was hidden behind the
ValidationError. No live agent or provider was called for these replays.

## Both end-to-end fixes integrated: detection, channel and service

The detection fixes for the simulation's bugs 1 to 6 (`docs/STEM_DESIGN.md`, section 33) and the channel and service
fixes above were merged into the development branch together, on 22d6a5b. The two branches change no common file under
`src/`, and they extend different functions of `scripts/arena/run_arena.py`.

An independent verification of the merged tree rejected one part of it. The detection branch had reported the maa-e1a
and mai-e1 substitutions "not applicable" (outside the transport count) through a harness reading that took a symbol
for unstated unless an "x = value" binding stated it. Its probe round showed the rule excusing real misses: a
substitution of the request's g in `E = m × 6.81 × 20 = 98.1 J`, with the mass stated only as "a ball of mass 0.50 kg",
and a slip in `E = 0.5 × k × 0.15² = 5.25 J`, with k stated only as "a spring of constant 200 N m⁻¹", went from 27 of
29 on 22d6a5b to 27 of 27. The rule is withdrawn (`docs/STEM_DESIGN.md`, section 33.3): every injection no finding names
is a miss, and when the receipt names the injected claim undecided the failure reason quotes it. The two substitutions
were then traced to their causes. The mai-e1 one is now named: an integer power beyond 12 of a closed value
(`(1 + 0.065/12)^{-60}`) is one value, and a decimal the answer states in prose for the quantity it named by a symbol
("Let $M$ be the monthly payment in euros." … "Her monthly payment is €352.19.") is a stated root of the equation in it.
The maa-e1a one stayed a miss in this repair: deciding it needed readings outside the encodings then (section 33.2,
item 7). A second verification rejected two of this repair's results, and the second repair below supersedes them.

Measured once on the repaired tree, on fresh copies, with no live agent or provider called:

- **Default suite:** 5,540 passed, 45 deselected (the stress selection), 4 expected failures (the same four as on
  22d6a5b). That is 22d6a5b's 5,264 tests and 4 expected failures, every one still collected (one parametrized id in
  `tests/integrity/test_integrity_round1.py` carries a UUID drawn at collection, so it reads differently each run), plus 276 new tests
  (145 detection tests in `tests/stem/test_e2e_run1_detection.py`, 131 channel and service tests). The arena rule tests
  (`scripts/arena/test_arena_rules.py`, run by path) give 39 passed.
- **Recorded rounds**, record by record against 22d6a5b (findings and messages compared with ids masked): r1 30/30,
  r1-adv 150/151, r2 to r6 46/46 and r7 177/177, as on 22d6a5b. Every record is identical except the nine records of r7's
  mai-t13 (its genuine answer and its eight variants), which each lose four ST-UNDEC-001 warnings that named
  `4000(1.003)^{60}`, `4000(1.003)^{132}` and `4000(1.003)^{144}` as integer powers beyond 12: the powers are now read,
  and those relations stay undecided for their ellipses (`4787.58…`), so no check is added and no finding or verdict
  changes otherwise.
- **The verification's probe round** (four answers, 29 transmissions): 27 of 29, the substitution of g and the slip with
  k listed as misses, as on 22d6a5b.
- **The simulation's round** (run1): transport 119 of 134, where 22d6a5b gives 114 of 134. Of the 102 injected faults,
  101 are named. Five of the six detection bugs are now detections: the ch-e1b slip and substitution are INT-SUBJ-001
  on s1.2 (`10^(−8.2) = 9.31 × 10⁻⁹`, and `10^(−8.5) = 6.31 × 10⁻⁹` for the substitution); the mai-e1 slip is
  INT-SUBJ-001 on m10.1 (`21\,131.40 − 18\,000 = 6131.40`, engine counterexample c = 15657/5, r = 30657/5); the mai-e1
  substitution is INT-SUBJ-001 on m3.1 and m5.1 (the changed annuity equation's root is 29.75, not the €352.19 stated
  for the payment; stem-sol UNSATISFIABLE); the hi-e1a misquotation is INT-REQ-003 on h1.5 (peer:maa-e1a holds all of
  its words but 'aly'). The maa-e1a substitution is the one miss: its marker now leaves the part label out, so m3.1
  carries it, and the failure reason quotes the receipt's ST-UNDEC-001 (a symbolic power) on m3.1. The other 14
  failures are the 14 syntheses. Each is now a REJECTED receipt naming INT-REQ-009 and INT-SYNTH-014 for every
  synthesized claim, not an exception; they stay failures because the simulation's combinator wrote free text in
  `transformation`. No genuine answer or peer relay gained an error-level finding: the 12 genuine receipts with errors
  are the same as on 22d6a5b, and the 14 additional receipts with errors are the rejected syntheses. ch-e1b, maa-e1a and
  mai-e1 gain six STEM checks, all of which hold (mai-e1's payment root among them).
- **The engine over HTTP**, using the simulation's own harness with one change: its HTTP leg names the policy that
  each pipeline result's `limits` record stands for, as contract 0.3 says a replaying caller must. All 245
  genuine-pass engine problems decide as in the pipeline (217 `linear`, 7 `nonlinear`, 21 `joint`), each matches the
  in-process result of the same payload, and each signature verifies. Posted without a policy, the eight problems of
  bug 8 still get the documented linear answer (seven UNSUPPORTED E201, one INVALID_FORMALIZATION E300 to E302). On
  22d6a5b the same harness, with its HTTP leg unchanged, gives 8 of 240 problems deciding differently. The frozen
  tree's 301 problems included 45 translator probes and 16 more translated claims of its older translator. The checks
  the repair adds (mai-e1's payment root, under `nonlinear`, and integer powers beyond 12) decide over HTTP under
  their named policy as in process, with signatures that verify.

## The second repair of the end-to-end detection fixes

A second independent verification of the repaired tree rejected three of its results and found a false-error class:

- **The ch-e1b substitution was not detected.** The recorded fault, `At pH 8.2: [H⁺] = 10^(−5.2) = 6.31 × 10⁻⁹ mol dm⁻³ [1]`,
  still held: a calculation with no unit stated in a unit is read as written and in SI (`docs/STEM_DESIGN.md`, section 6.4), and
  10^(−5.2) read as a bare number in SI, in mol m⁻³, is exactly that value in mol dm⁻³. The first repair had changed the harness's
  injection instead of the detection (an exponent of ten moved its first decimal digit, `10^(−8.5)`; the run1 count above rests on
  that), and a test asserted that the recorded line was no error.
- **The maa-e1a substitution was still a miss** (`P(t + 4) = P₀e^(k(t + 1))`).
- **False errors on correct decimal powers stated with ASCII units** (`[H+] = 10^(-3.3) = 5.01e-4 mol dm-3`): `dm-3` and `s-1`
  were read as subtractions. That misreading is older than the repairs (`v = 6 ÷ 2 = 3 m s-1` was an error at 22d6a5b); reading the
  decimal powers exposed it.

Each is fixed at its cause (`docs/STEM_DESIGN.md`, section 33, items 1, 5 and 6, and 33.3). The injection is the base one again
(the leading digit of every figure moves by 3, an exponent of ten included), and an antilogarithm stated as a concentration is the
concentration in mol dm⁻³, the unit of the pH scale, so the recorded fault is UNSATISFIABLE and the test asserts the error. An
application of an exponential model that the answer or the request defines is checked as a model evaluation (`stem-mod`). A unit
exponent written in ASCII and glued to its atom is the atom's power. Measuring the model reading found two more false errors in its
area, and both are fixed (item 5). Consecutive evaluations of a function the text defines were an algebra step under the product
reading: `N(10) = 200`, then `N(15) = 100`, was refuted, as it already was at 22d6a5b. A letter defined as two models was read with
its last definition only.

Measured once on the staged tree, on fresh copies of every round, with no live agent or provider called:

- **Default suite:** 5,667 passed, 45 deselected (the stress selection), 4 expected failures (the same four as on 22d6a5b), in 208 s.
  All 5,268 tests that 22d6a5b collects are still collected, apart from the one parametrized id in
  `tests/integrity/test_integrity_round1.py` that carries a UUID drawn at collection. There are 403 new ones: 165 detection tests in
  `tests/stem/test_e2e_run1_detection.py`, 56 in `tests/stem/test_model_evaluations.py`, 50 in
  `tests/stem/test_ascii_unit_exponents.py`, 1 front-end safety case for the new `stem/models.py`, and the 131 channel and service
  tests. In the detection file, the tests that the verification rejected are replaced by stricter ones (section 33.4). The arena rule
  tests (`scripts/arena/test_arena_rules.py`, run by path) give 39 passed.
- **Recorded rounds**, compared record by record with 22d6a5b (findings and messages compared with ids masked): r1 30/30, r1-adv
  150/151, r2 to r6 46/46 and r7 177/177, as on 22d6a5b. Rounds r1 to r6 are identical. In r7, 18 records differ. The nine records
  of maa-p7b (its genuine answer and eight variants) each gain three model checks, all SATISFIABLE (`C(8) = 800`, `C(T) = ½C0`,
  `C(40) = 1600 × 2^(−5)`). The nine records of mai-t13 each lose the four ST-UNDEC-001 warnings of the first repair. No record
  gains or loses an error.
- **The verification's probe round:** 27 of 29, the substitution of g and the slip with k listed as misses, as on 22d6a5b.
- **The simulation's round (run1):** transport 120 of 134, against 114 of 134 on 22d6a5b. All 102 injected faults are named (96 on
  22d6a5b), each as the harness injects it. The six detection bugs:
  - ch-e1b slip: INT-SUBJ-001 on s1.2, `10^(−8.2) = 9.31 × 10⁻⁹ mol dm⁻³`, UNSATISFIABLE.
  - ch-e1b substitution: INT-SUBJ-001 on s1.2, as recorded, `10^(−5.2) = 6.31 × 10⁻⁹ mol dm⁻³`, UNSATISFIABLE.
  - maa-e1a substitution: INT-SUBJ-001 on m3.1, `stem-mod-1` UNSATISFIABLE (e^(3k) = 1 would be needed, with k = 2.05 to 3 s.f.).
  - mai-e1 slip: INT-SUBJ-001 on m10.1.
  - mai-e1 substitution: INT-SUBJ-001 on m3.1 and m5.1.
  - hi-e1a misquotation: INT-REQ-003 on h1.5.

  The 14 failures are the 14 syntheses, each a REJECTED receipt naming INT-REQ-009 and INT-SYNTH-014. The genuine answers and the
  two peer relays are all functional. The 12 genuine receipts with errors are the same as on 22d6a5b. Against the first repair's
  replay, 9 records differ. The ch-e1b substitution is named as recorded (`10^(−5.2)`, not `10^(−8.5)`). The maa-e1a substitution is
  now functional. The other seven maa-e1a records each gain two model checks, both SATISFIABLE.
- **The engine over HTTP:** the simulation's own harness, with the policy-naming HTTP leg of the first repair, was run on the staged
  tree. It started the service as shipped on 127.0.0.1 and used a copy of run1. All 248 genuine-pass engine problems decide as in
  the pipeline, and each matches the in-process result of the same payload with a signature that verifies. The policies are 217
  `linear`, 21 `joint` and 10 `nonlinear`. That is the first repair's 245 plus maa-e1a's two model checks (`nonlinear`) and
  mai-e1's payment root. The harness's own bug list holds only the 14 rejected syntheses: none of the six detection bugs, no crash
  and no HTTP difference. Separately, the 15 checks this repair adds or changes were posted with their named policy through the
  service app's test client: maa-e1a's model checks on the genuine and the injected answer, ch-e1b's concentration readings, three
  ASCII-unit lines and two two-model lines. Each decides as in process.
- **The verification's own probe list** (48 STEM answers): 47 give the expected outcome. The one that does not is
  `c = 0.25 × 4 = 0.001 mol dm⁻³`, which holds in SI (1 mol m⁻³). The product has no unit, so reading its operands in SI is an
  admissible reading of section 6.4, and dropping that reading would turn correct work into errors (`d = 20 × 25 = 0.5 km`, or
  `c = 0.0969/0.0024 = 0.0404 mol dm⁻³` with the volume in m³). It is recorded as a known gap (`docs/STEM_RESULTS.md`, section 9),
  not fixed.

## Summary of the overseer verdicts, rounds 1 to 7

| Round | Material | results-audit | communication-fidelity | adversarial-live | translation-fidelity | New findings (blocker / major / minor) | Fixed in the fix round (fixers' count) | Harness as run for the overseers |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 4 tasks (English, History) | 0.909 | 0.909 | 0.850 | not run | 33 (8 / 15 / 10) | all, with regression tests | r1 20 / 22, r1-adv 108 / 127 |
| 2 | 6 tasks, History-to-English peer exchange | 0.56 | 0.488 | 0.612 | not run | 49 (2 / 24 / 23) | 49 | 34 / 34 |
| 3 | 6 tasks, English-to-History peer exchange | 0.727 | 0.769 | 0.871 | not run | 37 (0 / 17 / 20) | not counted | 41 / 41 |
| 4 | 6 tasks, History-to-English peer exchange | 0.387 | 0.575 | 0.89 | not run | 44 (1 / 26 / 17) | 42 | 41 / 41 |
| 5 | 6 tasks, English-to-History peer exchange | 0.366 | 0.617 | 0.79 | not run | 45 (0 / 27 / 18) | 39 | 41 / 41 |
| 6 | 6 tasks, History-to-English peer exchange | 0.724 | 0.49 | 0.8329 | not run | 36 (0 / 21 / 15) | 33 | 46 / 46 |
| 7 | 22 answers in 19 tasks, 16 agents, 3 peer groups | 0.532 | 0.4246 | 0.7477 | 0.6384 | 66 (3 / 45 / 18) | 40 | 148 / 161 |

The next round's overseers confirmed the fixes lens by lens: 44 of the 49 round-2 findings were
confirmed fixed in round 3; the round-4 lenses confirmed 10, 8 and 17 earlier findings fixed, the
round-5 lenses 13, 12 and 16, the round-6 lenses 18, 15 and 15, and the round-7 lenses 8, 13 and 13
(results audit, communication fidelity and adversarial live, in that order).

**The 98% bar was not reached.** The loop's pass condition, every lens at 0.98 or above in one round,
was not met in any of rounds 1 to 7, and no single lens reached 0.98 in any round. The highest
verdict was 0.909 (round 1, results audit and communication fidelity); in round 7 the four lenses
gave 0.532, 0.4246, 0.7477 and 0.6384. The harness's 100% on most recorded rounds is a different
measure: it checks that the hub delivered and decided every transmission and named every injected
fault, not that every finding is true.

## What remains open after round 7

- **Round-7 findings not yet fixed.** The fixers reported 40 of the 66 findings fixed; the round-8
  overseers will confirm or reject each. The items below are the ones written up as not done.
- **Overseer build.** The validation that refuted correct false_conflict accusations, the gold
  labels for translation_ungrounded and translation_circular, the inspection guide's rule that any
  reading encoded as a problem is unfaithful (the translator's policy encodes the argument structure
  of a literary point), and issuing dossiers from the main code are the overseer build's to change.
  The main code now provides `split_by_gloss` and `gloss_content` (exported from
  `epinoic_logic.integrity`) and `engine.runner.circular_premises` and `assumed_grounding` for it to
  reuse.
- **STEM notation.** Exponent marks are folded away ('10³' is read as '10'), so a changed exponent is
  not seen as a figure change; significant figures in scientific notation are not covered by the
  stated-precision rule; general worked equations (Economics, Business, Geography and the other
  generic-branch subjects) are named undecided but not decided, since only elasticities and margins
  are; from/to pairs with unit symbols ('rises from 4.0 Ω to 2.4 Ω') and
  a stated value whose computation sits elsewhere are silent. These belong with the STEM build's own
  notation and equation readers when it merges.
- **Translation.** Translation accuracy (143 of 224) has not been re-measured: that needs the live
  translators to re-translate with the new prompt, and no live provider was called. The prompt half
  of the support-graph fix (keep the stated direction, never treat each support as sufficient on its
  own, flag rather than invent a link) is not written. The component versions in `version.py` were
  not bumped, although the round-7 fix round changed the prompt and pipeline, the eligibility rules
  and the engine's diagnostics. (Since done: the review fixes bumped them to engine 0.4.0, policy 2026.10-v4 and
  translator 0.4.0, and every result now binds the build, schema and policy identity, so a result of an earlier
  release is never taken as current.)
- **Recorded round data.** The recorded r7 fixtures and syntheses cite the earlier parse's ids (200
  fixtures unserved, 15 syntheses charged INT-LEDGER-001 and INT-LEDGER-002), and the recorded peer
  relays of r2 and of r4 to r7 differ from the current parse; none was re-recorded, so the harness
  stays read-only on the rounds. Rounds from 8 on should record `claim_text_sha256` for every
  fixture.
- **Peer relay files.** Every recorded relay of rounds 2 to 7 (`relayed/<task>.json`, the only file
  the peer-dependent agent may read) also carries the router's records: the plan, the request, the
  peer's delivery receipt with every finding message and formal check, and the relay receipt. A
  dependent agent could therefore read hub findings as content, and in run1 one repeated a false
  INT-SUBJ-001 to the student (round-7 router and envelope review). Fixed in the harness:
  `relay_peer.py` now writes the delivered payload, its document id and the relay status only, and the
  router's records to `router/<task>.json`, which no agent reads. The recorded rounds were not
  re-recorded: a replay names the router-only fields of each recorded file (`router_fields_exposed`
  on the recorded relay check, and in summary.md), without changing any count. The dependent answers
  of rounds 2 to 7 are to be read as written by agents that could read their peer's receipt.
- **Claim ids.** English and History claim ids are still positional per report, so two English-branch
  agents in one group would collide; the generic fold claim keeps the unqualified 'g.tail'.
- **Quotations and credit.** An uncredited quotation found in no supplied text, whose sentence credits
  no source ('the birth rate halved in a decade', «crecen amigos»), is still only CORE-SRC-003; the r5
  hi-p4 INT-REQ-003 above reads as a false error from the round-7 altered-quotation rule; a Business
  answer's credit through "'s view that" (bm-p7ac) gets no attribution finding.
- **Ledger.** INT-LEDGER-020 gives a false warning when a claim quotes one document twice without a
  locator; INT-LEDGER-024 counts formula constants, document references, list numbers and age-band
  labels as dropped figures.
- **Notes.** A multi-sentence 'Note:' paragraph is not yet left out of the word and paragraph bounds
  on every branch, and 'Limit:' or 'Caveat:' leads and source caveats without a lead are read as
  notes only on the History branch.
- **Carried from round 4.** The requested verdict is still recognised from a closed vocabulary, not
  the request item's own terms (HI-STR-001 stays on hi-t13).
- **Performance.** The round-6 finding that large answers take more than 5 s, growing with the number
  of formal checks, is deferred to the optimisation checks.

## Stress, the next rounds and the optimisation checks

No stress iteration was run after the bug-fix rounds, by the founder's instruction (no stress tests
after bug fixes). `docs/STRESS_RESULTS.md` therefore ends with the stress iteration after the
round-2 fix round; the caching added in the consolidation pass and every later fix are not
stress-measured there. The informal before-and-after latency comparisons some fixers made during
the round-4 to round-6 fix rounds, on a machine shared with the other fixers, are not stress
results; in round 7 no stress test or latency benchmark was run.

Rounds 8 to 10 run after the STEM build and the overseer build merge into the main code, on the
merged infrastructure. From round 7 every lens's verdict counts: four lenses, five once the STEM
build joins. The optimisation checks run last, after every bug-testing round.

## Honesty notes

Translation outcomes depend on the translation provider (here, fixtures written for the genuine
outputs; no live provider was called) and are reported apart from the infrastructure rate. An
ENTAILED verdict proves only that the encoded conclusion follows from the encoded premises under
this configuration; the record says how many of those premises are ungrounded or rest on authority no
check validated, and a vacuous or circular encoding, or one that omits a figure a source asserts, is displayed as
INVALID_FORMALIZATION, never as a verdict. Formal entailment is not permission to release: the release assessment
is a separate record. An AMBIGUOUS_TRANSLATION is never shown as verified. The harness rate does not judge whether a finding is
true. A specialist's or an overseer agent's own report is advisory: only a signed engine result or a
deterministic re-check confirms anything. Transport, fixture coverage, translation fidelity (only where
adjudicated) and the claim counts are separate measures, never one rate; a replay that loses recorded translations,
or serves them without a recorded claim-text digest, is qualified in its summary.
