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
  and the engine's diagnostics.
- **Recorded round data.** The recorded r7 fixtures and syntheses cite the earlier parse's ids (200
  fixtures unserved, 15 syntheses charged INT-LEDGER-001 and INT-LEDGER-002), and the recorded peer
  relays of r2 and of r4 to r7 differ from the current parse; none was re-recorded, so the harness
  stays read-only on the rounds. Rounds from 8 on should record `claim_text_sha256` for every
  fixture.
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
this configuration; the record says how many of those premises are ungrounded, and a vacuous,
circular or unasserted encoding is displayed as INVALID_FORMALIZATION, never as a verdict. An
AMBIGUOUS_TRANSLATION is never shown as verified. The harness rate does not judge whether a finding is
true. A specialist's or an overseer agent's own report is advisory: only a signed engine result or a
deterministic re-check confirms anything.
