# Arena results: isolated specialist agents communicating through the infrastructure

The arena is the contained environment in which real specialist agents, configured only
from the English and History knowledge documents and isolated from the verification code,
produce answers to router tasks; every output then crosses the hub exactly as it would in
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
not already carry. Translation outcomes depend on the translation provider and are reported
separately from the infrastructure rate.

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

## Round 4 (six fresh tasks, including a History-to-English peer exchange)

Fresh outputs from the isolated agents: English paragraphs on Wordsworth's 'Composed upon
Westminster Bridge' (personification and the turn) and on a comic narrator's voice in a novel
opening, History responses on the Treaty of Versailles and Weimar instability (to what extent) and
on the 1929 crash and German unemployment (dated and quantified), and a peer exchange: the History
specialist's context paragraph on London in 1802 was relayed through the hub to the English
specialist as the document peer:hi-p3 and quoted in its reading of the sonnet's 'smokeless air'.

| Measure | Value |
| --- | --- |
| Harness, genuine outputs, 6 mutations each and the peer relay (r4), as run for the overseers | 41 / 41 functional (100%) |
| Round-4 overseer verdicts (results-audit / communication-fidelity / adversarial-live), on the round-3 fixes | 0.387 / 0.575 / 0.89 (round 3: 0.727 / 0.769 / 0.871); 44 new findings (1 blocker, 26 majors, 17 minors) |

The results audit found that the harness's own rule hid wrong receipts. A mutation counted as
functional whenever the expected code appeared anywhere on the receipt: hi-p3's genuine text already
raises CORE-SRC-003 for its own 'smokeless air', so its three quotation mutations would have passed
even if the injected quotation had not been named. Findings a mutation carried beyond the genuine
record were never reported, and the summary listed only the error codes of genuine transmissions,
with no claim ids, messages or warnings. What the harness fix changed (`scripts/arena/run_arena.py`,
regression tests in `scripts/arena/test_arena_rules.py`, run by path as
`python -I -m pytest -q scripts/arena/test_arena_rules.py`):

- **The expected finding must name the injection.** Each mutation knows what it injected (the
  invented words, the altered quotation, the self-certification, the false arithmetic, the false
  order). A delivered claim whose text or quotation excerpt carries those words is an injected claim
  (`injected_claim_ids`). A mutation is functional only when a finding of the expected code (for the
  self-certification, one of the self-report codes) names an injected claim, quotes the injected
  words or, for the self-certification paragraph, names its place ('paragraph 5, sentence 1'), and
  the genuine record of the same task does not already carry that finding. The findings that
  qualified are kept as `named_by`; a failing record says why (`failure_reasons`).
- **Findings beyond the genuine record are reported.** Each mutation record lists the findings the
  genuine record does not carry and that do not name the injection (`unexplained_findings`; a
  genuine finding that changed keeps its old message), and the errors and warnings of the genuine
  record that the mutation lost (`baseline_findings_absent`). A crossed word bound carries the
  genuine measurement and the number of words the mutation added, so it can be checked by
  subtraction (hi-t8: 186 genuine words + 17 appended = 203 measured). These are listed in
  results.json (`mutations_with_unexplained_findings`) and summary.md; they do not change the rate.
- **The genuine section carries every error and warning** of each genuine transmission and peer
  relay, with its claim ids and message (`genuine_with_errors`: `codes` are the error codes,
  `warning_codes` the warning codes, `findings` the findings).
- **A peer-dependent task's mutations are checked against the same pool as its genuine reply.**
  On each mutation's own hub task the peer's genuine report is now verified with the peer's own
  translations, as in the genuine pass. Before, it was verified with the dependent task's fixtures,
  so the peer contributed nothing to the cross-agent pool and every r2 en-p1 mutation silently lost
  the genuine cross-agent INT-GLOSSARY-005 between h1.1 and the English claims. The new diff
  surfaced this.

The same recorded rounds under the stricter rule, on the code as it stood during the round-4 fix
round (the channel, History and English fixes were landing at the same time):

| Set | Before the harness fix | After |
| --- | --- | --- |
| r4 | 41 / 41 | 41 / 41; every quotation mutation of hi-p3 is named on the injected claim, not by the genuine CORE-SRC-003 |
| r3 | 41 / 41 | 41 / 41 |
| r2 | 41 / 41 | 41 / 41 |
| r1 | 26 / 26 | 26 / 26 |
| r1-adv | 150 / 151 | 148 / 151 |

The two new r1-adv failures are real receipt gaps that the old rule hid. hi-t2-long-bullets-nopunct
is a 6,500-character bullet block with no sentence punctuation, so the wrong_arithmetic and
chronology_error sentences join its last bullet. The History parser delivers that bullet as claim
h2.62, but the formal check reads the whole block as one sentence. INT-SUBJ-001 is then raised with
no claim ids and quotes only the first 160 characters of the block, so nothing on the receipt says
which statement is false. The packs and the channel need to quote the clause the check was built
from and carry the claim ids; that change is outside the harness and is handed to their owner. The
empty response is still the third failure.
