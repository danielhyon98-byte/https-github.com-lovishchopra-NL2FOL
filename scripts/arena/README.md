# Arena harness

The arena replays real specialist answers through the hub exactly as production would carry them, adds injected faults,
and reports what the hub did. The per-round record is `docs/ARENA_RESULTS.md`.

| File | What it does |
| --- | --- |
| `run_arena.py` | Feeds one round through the hub and writes `<round>/results.json` and `<round>/summary.md` (definitions in its docstring) |
| `relay_peer.py` | Records the peer relay a peer-dependent agent reads (`<round>/relayed/<task>.json`: the delivered payload, its document id and the relay status only) and the router's record of it (`<round>/router/<task>.json`: the plan, the request, the peer's receipt and the relay receipt; no agent reads it) |
| `revision_feedback.py` | Records the infrastructure's feedback on every genuine answer (`<round>/feedback/<task>.json`: whether a revision request was issued and, if not, why; the signed block; `rendered`, the exact message the specialist reads, and its digest; the flaws), built through an audited hub from the answer's receipt and a signed task audit, never from an agent (design section 53 of `overseer/docs/OVERSEER_DESIGN.md`). The pipeline sends `rendered` alone as the specialist's next turn, after its own answer, and records the revision in `<round>/revisions/<task>.json` |
| `list_claims.py` | Lists the claims of an answer as transmitted, under the claim ids the hub delivers (below, "Claim ids in a group"); with `--json`, each claim text's digest, the file's group, the files of the group delivered before it and whether its ids are agent-qualified, and the synthesis format the combinator writes (`synthesis_format`: the combinator sub-project's exported instructions, checked against the synthesis contract; `--instructions <dir>` reads a given export, which must be this repository's combinator release unless `--allow-other-release`) |
| `stem_mutations.py` | The STEM fault injections (STEM subjects only) |
| `stress_arena.py` | Replays a round under load (`docs/STRESS_RESULTS.md`) |
| `bind_adjudications.py` | Binds an adjudicator's judgments of translation fidelity to the recorded translations they judged |
| `bind_translations.py` | Records with each translation fixture the digest of the claim text it was produced for (`claim_text_sha256`), from the listings the translation agent was given or, as the recording step, from the current parse ("Replay configuration", below) |
| `test_arena_rules.py` | Regression tests of the functional rule and the reporting (run by path, below) |

A round directory holds `specialists/*.json` (the answers), and optionally `translations/*.json` (recorded translations,
with `claim_text_sha256` binding each to the claim text it was produced for, written by `bind_translations.py` when the
translations are recorded), `syntheses/*.json`, `relayed/*.json`, `router/*.json`, `tasks.json` and
`adjudications/translation_fidelity.json`.

## Claim ids in a group: what the listing prints and what a fixture is keyed by

Write translation fixtures and combinator citations with the claim ids `list_claims.py` prints: they are the ids the hub
delivers. The reports of one group (one hub task) are delivered in `run_arena.py`'s order (name order, a peer-dependent
task after the task it depends on), and the hub parses a STEM report whose claim ids a report of another agent delivered
before it already holds with its ids qualified by its agent (`channel.bus.needs_qualified_ids`, integration gate 1; a
History or English report likewise since integration gate 3, `h1.1@<agent>`, `p1-point@<agent>`): when
a Chemistry and a Physics specialist of one group both write `s1.2`, the Physics report, delivered second, is delivered
as `s1.2@physics-specialist`. `list_claims.py <round>/specialists/<task>.json` therefore parses the file after every
member of its group delivered before it (given on the command line or not, each taken as delivered), with the subject,
task type and request text the group's plan gives its agent, as the hub parses it, and says so: the text listing names
the files delivered before it and whether its ids are qualified, and `--json` carries `group`, `delivered_after` and
`ids_qualified`. `--agent-view` renders the reports in the order given, each under the ids the hub delivers it.

`run_arena.py` keys a recorded translation by its claim id, and a STEM claim has two forms of its id: `s1.2` and
`s1.2@<agent>` (a History or English claim likewise: `h1.1` and `h1.1@<agent>`, `p1-point` and `p1-point@<agent>`). The genuine pass and the delivery pass deliver the group's reports on one hub task, so the second STEM
report of a group carries the qualified form; a mutation is delivered on a hub task of its own with only its peer's
report before it (a peer-dependent task), so there the same claim carries the unqualified form unless that peer holds
its id. A translation recorded under either form of one agent's STEM claim id serves that claim
under the other: the pipeline is given the same recorded translation with its problem naming the delivered id
(`fixture_for_claim`; nothing else changes, and a problem naming any other claim is served as recorded, so it fails as
it would under its own id), and its claim-text digest binds it as any fixture's. Every record that served one names it
(`fixtures_served_under_other_id_form`: recorded id -> delivered id), the fixture coverage counts them
(`served_under_other_id_form`, with each file's map) and summary.md lists them on its fixture-coverage line. Ids a parser
writes in one form only are matched as written: the generic parser qualifies every id it writes, so a generic fixture
recorded as `g1.1` is an older parse's (round 7 holds 200 such fixtures) and stays unserved, as "Qualified runs" below
says ("never re-key them by bare claim id"); so does a fixture keyed by another agent's tag.

Integration gate, round 2 (correctness lens, major): the single-file listing parsed a file alone, so for the second STEM
report of a group it printed `s1.2`, which the hub never delivers; a fixture recorded from it was never served (the
verifier returned `CLAIM_OUT_OF_SCOPE`, the genuine record had no outcome, the run was qualified TRANSLATIONS_LOST) and,
its claim-text digest never captured, a mutation that changed the claim was served the genuine claim's translation;
a combinator citing `s1.2` for that agent cited the other agent's claim. The listing also left out the request text the
STEM parsers read, so a claim's role and assumptions could differ from the delivered report's (the lens's Physics
`Given:` line listed as evidence, delivered as quantitative); every one of round 7's 22 files is now listed as the hub
delivers it. Tests: `scripts/arena/test_arena_rules.py` (two STEM agents in one group).

A mutation is compared with its genuine record in the mutation's id form. A mutation of a group member is delivered on a
hub task of its own with only its peer's report before it (a peer-dependent task), so the second STEM report of a group
whose earlier member is not its peer is delivered there with its unqualified ids while its genuine record carries the
qualified ones. The genuine findings are read with this agent's tag dropped from their claim ids and messages
(`baseline_in_form`), so a genuine finding is never "unexplained" on the mutation record or "absent" from it for its id
form alone (before, a genuine `ST-UNDEC-001` warning of such a report was listed both ways on each of its seven
mutation records), and the rule that a finding the genuine record carries never names the injection holds for it. Such a
mutation is still checked without the other members' reports on its hub task, as before, so a cross-agent finding of
the genuine record (one naming another member's claim) still reads as absent from it; no recorded round has such a
group (r1 to r7's groups are pairs of a peer and its dependent).

## Peer relays: what the dependent agent reads

`relay_peer.py <round> <task>` relays the peer task's delivered report to the peer-dependent agent through the hub and
writes two files. `relayed/<task>.json` is the only thing that agent may read of its peer, and it holds exactly
`task_id`, `peer_of`, `delivered`, `relay_status` (the relay's transmission status, or `NOT_RELAYED` when nothing was
relayed), `document_id` (`peer:<peer task>`) and `payload` (the specialist_report/1.0 payload as delivered); the last two
only when a report was relayed (`run_arena.RELAYED_FILE_KEYS`). `router/<task>.json` is the router's record: the plan as
used, the request to the peer, the peer's delivery receipt (every finding, subject finding, constraint result and formal
check, with its message) and the relay's own receipt. Brief the dependent agent with the relayed file alone; the tool's
standard output is the router's (both paths, the statuses and the receipt's codes, no finding message).

A receipt is the router's to act on, not content for the agent: the round-7 router and envelope review found the
receipt, finding messages included, written into the relayed file, and a dependent agent repeating a false finding
(INT-SUBJ-001) to the student. Every recorded relay of rounds 2 to 7 (round 1 has none) carries the plan, the request,
the peer's receipt and the relay receipt that way; the recorded rounds stay read-only and were not re-recorded. A replay
reads only `delivered`, `document_id` and `payload` of a recorded file, and each recorded relay check
(`recorded_relay_checks` in results.json, the recorded peer relays in summary.md) names the file's other fields as
`router_fields_exposed`, so an answer written by an agent that could read its peer's receipt reads as one. It changes no
count.

## Synthesis format (the combinator's instructions)

The combinator agent's instructions are the combinator sub-project's (`combinator/`, package `epinoic_combinator`, a
separate agent with its own release): export them once per round and brief the combinator agent with them.

```
PYTHONPATH=combinator/src python -m epinoic_combinator.export --out <round>/combinator   # INSTRUCTIONS.md, output-format.json, MANIFEST.json
python scripts/arena/list_claims.py <round>/specialists/<task>.json --json --instructions <round>/combinator
```

Give the agent `INSTRUCTIONS.md` and the one JSON document its "What you receive" describes, the one the combinator's
runner gives its agent. For a group of two to sixteen reports (a peer group of one request, the port's combined answer)
`list_claims.py` prints it, rendered by the sub-project's own code in its own isolated process, each report under the
claim ids the hub delivers it (above, "Claim ids in a group"), so the combinator cites the ids the hub holds:

```
python scripts/arena/list_claims.py --agent-view <round>/specialists/<task>.json <round>/specialists/<peer>.json --instructions <round>/combinator
```

A task of a single report is no combinator input (the runner combines two reports or more), so its agent is briefed with
the `--json` listing, which maps onto that document as follows: `request` is `{"task_id": <group>, "request_id":
"req-<group>"}` (`request_id` of the listing; the group is the task id unless the task names one); the listing is one entry
of `sources`, with its `report_id` and `branch`, the specialist's `agent_id` and `subject` from the specialist file, and per
claim only `claim_id`, `role`, `materiality`, `certainty` and `text`. The listing's other fields (`eligible`,
`eligibility_class`, `supporting_claim_ids`, `source_refs`, `assumptions`, `advisory_verification_status`,
`claim_text_sha256`) and `synthesis_format` (the exported `output-format.json` under the pack's identity) are the arena's,
not part of what the runner shows its agent. The agent writes the output object to `<round>/syntheses/<task_id>.json`,
where `<task_id>` is the file name of a specialist file of the group (`specialists/<task_id>.json`), never the group id
the agent view's `request` names. A task of a single report writes to its own task's file. A peer group's combined
output (the one `--agent-view` answer for the whole group, citing claims of every report) is written once, to ONE
member's file; by convention the group's last task's, the deliverable, though either member's file gives the same
receipt. Write no file for the other member: one file per member is the format of the recorded rounds r1 to r7, which
the harness merges in group order, and a second file would add the combined claims again.

```
{"claims": [{"text": "...", "source_claim_ids": ["..."], "certainty": "established" | "probable" | "possible",
             "transformation": "carried" | "paraphrased" | "merged" | "narrowed" | "generalized"}],
 "dropped": [{"source_claim_ids": ["..."], "reason": "..."}],
 "conflicts": [{"claim_ids": ["...", "..."], "description": "..."}]}          (conflicts only when sources contradict)
```

and nothing else: no `report_id` (the runner refuses any key besides these three as `output_invalid`, `KIT-CB-002`). Recorded
rounds also carry `report_id`, written by the tooling before the combinator sub-project existed; the harness does not read
it.

- `transformation` is exactly one of those five words, a category of what was done to the cited sources, never a
  description of the edit. What each records is `TRANSFORMATION_MEANINGS` in `src/epinoic_logic/integrity/contracts.py`,
  word for word in the exported format: `list_claims.py` refuses (exit status 2) an export whose values or meanings are
  not the contract's, or whose files are not its manifest's. While `combinator/` is in this repository it also refuses
  an export that is not this repository's combinator release: the export's instruction pack (name, version, SHA-256)
  must be the one an isolated export of the sub-project writes, so a rewritten `INSTRUCTIONS.md` with a recomputed
  manifest is refused too, unless `--allow-other-release` explicitly allows another release's instructions (said on
  standard error). Only then can neither file drift from what this repository's hub and combinator accept. Without
  `combinator/` here (a split repository), only the manifest and `output-format.json` are checked against the
  contract; `INSTRUCTIONS.md` is then checked against its manifest only. Without `--instructions` it exports the
  sub-project of this repository in the sub-project's own isolated process (it never imports it).
- `certainty` is never stronger than the weakest cited source (INT-LEDGER-003); figures, units, marks, dates and
  quotations are kept exactly as the source states them (a figure restated in another unit or era is INT-LEDGER-023), and
  so are qualifiers, a frequency ("usually") or a bound ("at least") included (INT-LEDGER-026); a note, a
  self-certification, a decline or a question is never carried back as a claim (a source claim whose `role` is `other` is
  a note and is never cited in `claims`), and no verification label ("Verified:", "(checked)", "(Z3: proved)", "[OK]") is
  put on one (INT-LEDGER-029); a synthesized claim cites each source claim once (the combinator's runner refuses a
  repeated citation, KIT-CB-002); every source claim left out goes in `dropped` with a reason in words (a transformation
  word or "dropped" is no reason, INT-LEDGER-006); a contradiction is disclosed in `conflicts`, never merged
  (INT-CONFLICT-002 for formalized claims; a contradiction between claims in prose is named only through the figures a
  synthesis changes or drops, INT-LEDGER-023 and INT-LEDGER-024), and a conflict is listed only when the claims really
  disagree (one the hub finds no contradiction for is INT-CONFLICT-006, info). Every text is words: a blank text or one
  holding a control character other than a tab or a line break is out of contract (KIT-CB-002).
- Any other value (free text, an alias such as "joined", another spelling) is refused by the hub: the synthesis is
  REJECTED with INT-REQ-009 and INT-SYNTH-014 naming each claim, and it is not delivered. So is a file that is not JSON,
  a claim that is not an object, a missing field or a field the synthesis contract does not have.

The end-to-end simulation of 16 October 2026 named the field without its values, and its combinator wrote free text in
all 62 synthesized claims; the recorded rounds r1 to r7, whose combinator was told the values, carry one of them in all
202. The same instructions run in the sub-project's own runner (a provider on the cheapest tier), which refuses any
output out of contract with a named `KIT-CB` code before it leaves (`combinator/README.md`).

`run_arena.py` relays each group's synthesis to the hub as the JSON the router receives (`group_synthesis` passes the
combinator's fields on as written; it never builds the contract models itself), so the hub's contract validation decides
it. A malformed synthesis is a REJECTED receipt recorded with its findings, and, being genuine traffic that was not
delivered, a failed synthesis record whose `failure_reasons` name the codes; it is never an exception that stops the
round or leaves the record without a receipt. As written means the citations too: every `source_claim_ids` reaches the
hub unchanged, so a citation of a claim no delivered report holds is named by the hub (INT-LEDGER-001), and the relayed
synthesis lists the report of every delivered member of the group in `source_report_ids`, whichever member's file holds
the output. The harness adds only what the format leaves to it: the synthesized claim ids (`s0`, `s1`, ...; prefixed with
the task id when the group has one file per member), the student-facing text (the claims' texts joined), a left-out
`certainty` or `transformation` (relayed as `established` and `paraphrased`, the defaults since round 1; the hub still
names a certainty stronger than a cited source, INT-LEDGER-003) and, for a claim that carries no `evidence_refs`, the
references of its cited material sources whose excerpts its text reproduces word for word, read from every delivered
report of the group (`evidence_refs_copied` on the record).

Integration gate, round 1 (combinator faults): the harness kept only the cited ids the file's own member's report held
whenever one of them did. An invented citation beside a real one vanished before the hub saw it (no INT-LEDGER-001 on an
arena receipt, while the same claims relayed directly drew it), and a peer group's combined output lost its citations of
the other member's claims and listed one report (the simulation's round run1, group e1a: saved as `hi-e1a.json`, a
claim merging a mathematics and a History claim was charged INT-LEDGER-023 for figures "that occur in none of its cited
sources"; saved as `maa-e1a.json`, its History citation vanished). Either placement now gives the receipt the same
synthesis gets relayed directly (`scripts/arena/test_arena_rules.py`). On the recorded rounds the change moves one
receipt and no count: r1's en-t1 synthesis cites `p3-s02`, an id of the parse it was written against, beside ids the
current parse delivers, and now carries INT-LEDGER-001 for it (transport 30 of 30, as before; one more genuine record
with an error-level finding); r2 to r7 replay record for record as before.

**The combinator's published contract.** In the deployed path a synthesis reaches the hub only through the combinator's
runner and the port's check (`integration.combinator_port.check_output`), which refuse an output out of contract with a
named `KIT-CB` code before it leaves. The harness reads every syntheses file it relays by the same rules, in the port's
order (`run_arena.combinator_contract_problem`): protocol JSON read from the file's bytes (UTF-8, no repeated key, no
float) and an object (`KIT-CB-002`); a transformation outside the five words (`KIT-CB-003`); a key besides `claims`,
`dropped` and `conflicts` (the legacy `report_id` aside) and the port's schema (`KIT-CB-002`: at least one synthesized
claim; a text, a dropped entry's reason or a conflict's description with no visible character, or holding a control
character other than a tab or a line break, or a bidirectional embedding, override or isolate; a source claim cited twice
by one claim or named twice by one conflict; a claim id outside the port's alphabet; a field of the wrong kind or one the
contract does not have); a synthesis text over 49152 UTF-8 bytes (`KIT-CB-006`). A file that breaks one is named on the
synthesis record under `combinator_contract` (its file, code, reason and the position and rule, never the text) and in
`failure_reasons`, and the record is a failure whatever the hub's receipt says: the deployed combinator would never have
let it out. The synthesis is still relayed, so its receipt shows what the hub, the independent checker, does with it.
Two of the port's rules are left to the hub: the request ids and the instruction pack (the file is the message's body,
and the harness builds the rest), and whether a citation names a claim the delivered reports hold (`KIT-CB-004`). A
recorded synthesis cites the claim ids of the parse it was written against, so in a replay an id the current parse no
longer delivers is the replay's, not the combinator's; the hub names it (INT-LEDGER-001), and the record stays counted as
the hub delivered it. The integration gate's combinator review found the arena relaying, and counting functional, a
merged claim's text ending in a NUL and a right-to-left override, a paraphrase holding a bell and an escape, a dropped
reason holding a terminal escape, a blank reason and a claim citing one source twice; none of the recorded rounds r1 to
r7 holds one, so no recorded count moved.

```
python scripts/arena/run_arena.py <round>                           # results.json, summary.md; exit 0
python scripts/arena/run_arena.py <round> --fail-on-qualification   # exit 1 when the run is qualified (below)
python scripts/arena/run_arena.py <round> --without-task-record     # the replays' configuration before round 8's clearance, for comparison ("Replay configuration")
python scripts/arena/bind_translations.py <round> --listings <dir>  # record each translation's claim-text digest when the round is recorded
python scripts/arena/bind_adjudications.py <round> <judgments.json> --adjudicator "<who judged>"
```

Replay recorded rounds on copies only; the recorded rounds are read-only. A replay of recorded material measures
regression stability on that material, not generalisation: answers used to build a fix are a regression corpus, and
unseen tasks and paraphrases are reserved for evaluation.

## Separate measures

The harness never combines two measures into one rate. results.json carries them under `metrics`; summary.md lists them
under the headline, one line each, each with its own denominator.

| Measure | What it counts | What it does not say |
| --- | --- | --- |
| Transport (`metrics.transport`; the headline functional count) | Transmissions the hub delivered and decided: genuine traffic (genuine replies, peer relays, syntheses) delivered, injected faults named by a finding of the expected code on the injected claim, no INTERNAL_ERROR. Every injection no finding names is a miss in it (below) | Whether a finding is true, whether a translation is faithful, whether an answer is better |
| Fixture coverage (`metrics.fixture_coverage`) | Recorded translations this run served (the pipeline translated their claims with them) against those it lost, by reason: report not delivered, claim id no longer delivered, refused as stale, claim not eligible, dropped by the channel, verification failed; served translations bound to a recorded claim-text digest against those bound by claim id only | Whether the served translations are faithful |
| Translation fidelity (`metrics.translation_fidelity`) | Of the translations this run served that an adjudicator judged, how many were judged faithful; only judgments whose recorded digests match the translation and claim text served apply | Anything when the round has no adjudications: then it reads "not adjudicated" and no figure is given. The engine never decides fidelity |
| Claims (`metrics.claims`, per record `claim_measures`) | On the genuine pass, each delivered claim once: extracted; eligible for translation; attempted (a recorded translation offered); completed (a definitive verdict displayed); faithful (where adjudicated); approved (displayed ENTAILED with no error-level finding on the claim), with how many approved claims rest on an ungrounded premise, how many rest on any unresolved dependency (ungrounded, or a premise whose task or source authority no check validated) and how many adjudicated approved claims were judged unfaithful; release permitted (the outcome's release assessment, `ClaimVerificationOutcome.release`, permits releasing the answer on the claim's checks, with no error-level finding on the claim) | "Approved" is what the receipt presents as verified, not an application's release decision. "Release permitted" is that decision's rule (established premises, a current faithful review made with the evidence): a replay calls no fidelity reviewer, so it permits none |
| Latency (`metrics.latency`) | Hub processing time per transmission in this run, on this machine | A stress or capacity figure (`docs/STRESS_RESULTS.md` has those) |
| Cost (`metrics.cost`) | No provider is called: recorded fixtures only | Live translation cost |

Beside the measures, summary.md counts on the genuine pass the claims whose encoding got no verdict, by rule
(`withheld_verdicts`: E108 vacuous, E110 unasserted figure and E111 unencoded reason a source states, E112 circular, a
rounded figure at another precision than the source states, an exact or given figure widened), and, apart, the verdicts
that stand with the engine's advisory coverage warning (`advisory_coverage_warnings`: W110, W111; the encoding leaves
open a figure no source asserts, which the question may leave open on purpose, or, for W111, a conjunct of the judgement
that no premise links). Neither count changes the transport
measure.

## Replay configuration: what a replay runs as production does, and what it cannot

A replay runs what production runs wherever a recording allows it, and names what a recording cannot run, so a figure of
the replay is never read as one of a configuration it did not have. results.json carries it as `metrics.replay`;
summary.md gives it on one line, "Replay configuration", after the measures. None of it moves the transport measure.

- **The task record.** The harness's claim verifier declares a `task` parameter, as production's does
  (`integration.runtime.live_verifier`): the channel hands it the task record of the request each report answers
  (`fn(claim, report, task=...)`, `channel.bus._accepts_task`; the delivery pass's deadline verifier passes it on), and
  the translator validates a task-authority premise (`task_setting`, `arithmetic_fact`, `rubric_rule`) against the
  router's question as well as the supplied texts. Each outcome says whether its translation was validated against a task
  record (`task_record_given`); the configuration counts them. A harness that replaces `verify_claim` with a function
  that declares no `task` parameter is called as before, and its outcomes say no record was given. Before round 8's
  clearance the verifier kept the two-argument signature, so a replay validated such a premise against the supplied texts
  only and left the rest unvalidated: round 8's translation-fidelity lens found seven of the round's outcomes that were
  not production's for the same translations (ps-t14's unverified dependency `cr-obs`; E112 withheld verdicts resting on
  a task figure no check had verified). `--without-task-record` (`run_round(..., task_record=False)`) replays as the
  harness did then, for a comparison with the replays recorded before; the configuration says it was not passed.
- **The binding of each translation to its claim text.** A recorded translation is bound to the claim text it was
  produced for by the digest recorded with it (`claim_text_sha256` in the translations file); without one it is bound to
  whatever text its claim id carries in the run (`served_by_claim_id_only`, the run qualified FIXTURES_UNBOUND, below).
  Round 8's translations were recorded without digests: all 469 were matched by claim id only. Record the digests as a
  step of recording a round, right after the translation agents wrote their files:

  ```
  python scripts/arena/bind_translations.py <round> --listings <dir>     # the list_claims.py --json listings the agents were given (<dir>/<task>.json)
  python scripts/arena/bind_translations.py <round> --current-parse      # the listings list_claims.py prints now: only before any change to the code
  ```

  A fixture keyed by the other form of a claim id the hub may qualify takes the digest of the claim listed under that
  form; a fixture the listing does not hold stays unbound and is named; a recorded digest that differs from the
  listing's is a conflict (nothing written, exit status 2; `--force` replaces it); a listing of another report is never
  bound. Only the `claim_text_sha256` map changes, so a fixture's digest (`fixture_sha256`, which an adjudication names)
  does not move. The source of the digests is always named on the command line: the current parse is right only as the
  recording step, since a later parse may carry another text under the same id.
- **Retries.** A recorded translation is one provider output, and the fixture provider serves it on every attempt. When
  the pipeline rejects the first attempt with a retryable diagnostic and asks again, the retry is served the same output
  and fails the same way: the outcome is what the recorded output gives on its own, where production would retry with
  the diagnostics and a new output. Such a retry is never shown as one that ran: each outcome carries `attempts` and
  `retry_not_exercised`, and the configuration counts and names the genuine claims whose retry was not exercised (with
  the total over every variant). It is no qualification and no transport failure: the claim was delivered and decided.
- **Synthesis timestamps.** A synthesis is stamped when it is relayed (`relay_clock`, as the deployed combinator path
  stamps it), so it never precedes the reports it cites; the record carries the stamp (`synthesis_created_at`). Until
  round 8's clearance every synthesis was stamped 2026-10-11T15:00:00Z, and the time-order rule (INT-HANDOFF-016, which
  the overseer's audit runs over the journaled transfers and reports as OVS-DIV-002) named every synthesis of every
  replay made after that day.

## Injections no finding names

An injection no finding of its code names on the injected claim is a miss: a failure of the transport measure, listed
under `failures` with its reason. No rule takes a miss out of the count, whatever the cause. When the receipt itself names
the injected claim of a STEM mutation undecided (an ST-UNDEC finding: a relation outside the encodings, or a symbol with
no stated value), the failure reason quotes that finding and the record carries it as `undecided_on_injected_claims`, so
a miss that a limit of the encodings leaves reads as one; it is still a miss.

The code that must name a STEM injection depends on its site (round 8's clearance, STEM-integration finding 25;
`stem_mutations.py`, "Sites"). A figure in code (a fenced block, an inline code span), in a mark annotation ("M1", "(A1)",
"[2]") or on a line that states a mark is no site: the design never checks them as working, so the mutation takes the next
site. A site inside a quotation of another text is also named by INT-REQ-003 (the change is an altered quotation the hub
refutes; a relation in quotation marks is quoted text, never a root or a step), and a term of a sum in brackets right after
the value it forms by INT-SUBJ-004 (the STEM pack reads that sum at warning severity), beside the mutation's own code
(`StemInjection.site_codes`; `expected` itself is unchanged). On round c1 this credits maa-p8b's wrong unit inside the
Physics specialist's quotation and ch-t14's substitution in '7 on the left (1 + 6)', each named on its injected claim by
that code before and counted a miss; every mutated text of c1 and r7 is the one it was.

An earlier version of the harness reported such a STEM injection "not applicable" (outside the count) when its own
reading found no "x = value" binding for a symbol of the changed expression and no formal check moved. An independent
verification showed that this excused real misses: a substitution of the request's g in `E = m × 6.81 × 20 = 98.1 J`
(the mass stated only as "a ball of mass 0.50 kg") and a slip in `E = 0.5 × k × 0.15² = 5.25 J` (k stated only as "a
spring of constant 200 N m⁻¹"). That rule is withdrawn: its probe round replays 27 of 29 with both misses listed, as on
22d6a5b (`tests/stem/test_e2e_run1_detection.py`).

Every STEM injection moves the leading significant digit of one figure by 3, the exponent of a power of ten included
(`10^(−8.2)` → `10^(−5.2)`): the harness never steers an injection around a reading of the checks. An earlier version
moved such an exponent's first decimal digit instead (`10^(−8.5)`), because a change of the leading digit is a factor of
exactly 10³ that the SI reading of a stated unit absorbed; that raised the count while the recorded fault still passed.
It is withdrawn: the injection is the base one, and the checks name it at its cause (`docs/STEM_DESIGN.md`, section 33,
items 1 and 7, and 33.3). The marker leaves a part label out ("(b) "), as every claim does.

## Qualified runs

A run is qualified when its translation figures cannot stand for the recorded round's. The summary's title says so, and
results.json carries `qualified` and `qualifications`:

- `TRANSLATIONS_LOST`: recorded translations were not served (for example, claim ids changed after the parser changed);
- `FIXTURES_UNBOUND`: served translations carry no recorded claim-text digest, so each is bound to whatever text its claim
  id carries in this run (record the digests with `bind_translations.py` when the translations are recorded: "Replay
  configuration", above);
- `ADJUDICATIONS_NOT_APPLIED`: adjudications that do not apply to this run (their translation was not served, or a digest
  differs).

With `--fail-on-qualification` a qualified run exits with status 1. Use it for a translation-regression run: it fails
instead of reporting figures for a different set of translations. Re-record the translations (with `claim_text_sha256`,
from `list_claims.py --json`, written by `bind_translations.py`) and re-adjudicate them when extraction changes; never
re-key them by bare claim id. (The two
forms of one agent's STEM claim id, `s1.2` and `s1.2@<agent>`, name one claim of one parse; a fixture recorded under one
serves the claim under the other, named on the record: "Claim ids in a group" above. An adjudication names the
translation by its recorded id, and its verdict is counted for the claim it served.)

## Adjudications

`<round>/adjudications/translation_fidelity.json` is a list of judgments, or `{"adjudicator": "...", "judgments": [...]}`:

```
{"file": "hi-t13.json", "claim_id": "h1.4", "verdict": "faithful" | "unfaithful", "cause": "optional",
 "translation_sha256": "<digest of the recorded fixture judged>", "claim_text_sha256": "<digest of the claim text judged>"}
```

`task_id` may stand for `file` when only one answer carries that task id; `F` and `U` are accepted for the verdicts.
`bind_adjudications.py` writes the digests from the round's recorded translations; run it when the judgments are made. A
judgment applies only to a translation this run served whose digests match; anything else is listed under
`translation_fidelity.not_applied` with the reason, never counted.

## Delivery decisions

After the round's records are complete, `run_arena.py` runs the delivery policy (`overseer/docs/DELIVERY.md`) over every genuine
answer, on a hub of its own carrying a transfer auditor. The pass replays each group's genuine traffic in order and opens
a delivery session per answer. It adds no record and moves no transport count. Its hub and claim verifier are bound at
import, so a harness that replaces `RouterHub` or `verify_claim` never reaches it. The contained harness switches it off
(`DELIVERY_PASS = False`) while it replaces them; `deliveries` then says it was not run. The auditor's key ring holds the
arena's engine key under every key id the hub's own components sign under (`DELIVERY_ENGINE_KEY_IDS`: `hub`, `channel`,
`default` and `integrity`, the cross-agent checks'), as the contained harness's does. Until the integration gate's first
round it declared `hub` and `default` only, so every result the cross-agent checks sign was audited as untrusted
(OVS-RES-003) and its answer excluded (AUDIT_FAILED). Replayed on the recorded rounds the fix moves no delivery mode
(every answer is withheld, as no overseer agent is configured), but r4's hi-t8 and r7's lit-p7c are no longer excluded,
and r7's hi-p7c is excluded only for its own INT-SUBJ-001. results.json carries `deliveries`:

- the count per mode;
- per task: the mode, the label, the time to decision, the translation and overseer times, the formal path's reasons
  and claims, every candidate with its accuracy and whether it was chosen, the chosen answer, the signed receipt's id
  and whether it verifies, and whether the pass's receipt equals the genuine record's (status and codes);
- the pass's errors and its wall time.

summary.md has a "Delivery decisions" table with one row per task. The command line configures no overseer agent,
because the harness calls no model, and a replay calls no fidelity reviewer. So no formal path completes, and an answer
is withheld with its reasons. `run_round(round_dir, delivery_overseer={"pack": ..., "provider_factory": ...})` configures
overseer agents (tests only: scripted providers).

## Specialist revisions

`revision_feedback.py <round> --all` replays each group's genuine traffic on a hub carrying a transfer auditor and writes
`feedback/<task>.json` for every genuine answer, standalone and peer-dependent (never a synthesis). An answer whose receipt
and task audit hold no allowlisted flaw gets no feedback (`no_actionable_flaw`): the counted negative control. A round's
`tasks.json` may set `revision_rounds` per task (round 8: 1), which `group_plan` puts in the plan's budget; without it the
plan is the one it was. The pipeline then makes one cheapest-tier call per issued file and records
`revisions/<task>.json` (`task_id`, `agent_id`, `feedback_sha256`, the digest of the message the specialist read,
`response_text`, and the call's model, effort, knowledge-base version, bundle digest, times and tokens).

When the round holds `feedback/`, `run_arena.py` runs a revision pass of its own after the delivery pass: it replays the
genuine traffic again, re-issues every request and compares it with the recorded file (`recorded_feedback_checks`: the
flaws, the keep list and the rendered digest; a difference is "feedback differs from what the specialist read"),
delivers each recorded revision in reply to its request under `rep-<task>-rev1`, audits with the shadow, decides each
outcome (fixed, removed, evaded, persisted, not re-checked; flaws introduced, INT-REV-002 findings, claims lost; the next
step) and consolidates the original with its revision. `results.json` carries it under `revisions` and `summary.md` in
"Specialist revisions": answers checked, feedback issued, answers revised, the fix rate (fixed plus removed where allowed,
over the flaws fed back less those not re-checked), the specialist's median and p90 time, the negative controls and the
gates (feedback as read, no revision without a request, no OVS-FB-001, the shadow agreeing, originals unchanged,
persisting errors withheld and escalated). The pass adds no record and moves no transport count: the headline rate
excludes it. No fixture is served in it (no claim outcome is ever fed back, so the flaws do not depend on one).

## Tests

```
python -I -m pytest -q tests/e2e/test_arena_revisions.py   # the specialist revisions: feedback files, the revision pass, the headline unchanged, feedback as read, the round's budget
python -I -m pytest -q scripts/arena/test_arena_rules.py   # the functional rule and its reporting, what a peer relay file may hold, the synthesis relay (citations as written, the combinator's contract), the delivery pass's key ring, two STEM agents in one group (the listing's delivered ids, a fixture under either form of a STEM id, mutations compared in their id form), and the replay configuration (the task record passed, retries not exercised named, syntheses stamped at relay time, bind_translations.py)
python -m pytest -q tests/e2e/test_arena_measures.py        # the separate measures, qualification, adjudications (default suite)
python -m pytest -q tests/e2e/test_arena_deliveries.py      # the delivery decisions in results.json and summary.md (default suite)
python -m pytest -q tests/stem/test_arena_stem_mutations.py # the STEM injections (default suite)
python -m pytest -q tests/stem/test_c1_handoff_mutation_sites.py # no STEM site in code or marks; the code a quotation or a bracketed sum is named by (default suite)
python -m pytest -q tests/stem/test_e2e_run1_detection.py   # the e2e run1 injections: all six named, each as the harness injects it
```
