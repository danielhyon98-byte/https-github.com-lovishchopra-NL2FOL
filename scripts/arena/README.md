# Arena harness

The arena replays real specialist answers through the hub exactly as production would carry them, adds injected faults,
and reports what the hub did. The per-round record is `docs/ARENA_RESULTS.md`.

| File | What it does |
| --- | --- |
| `run_arena.py` | Feeds one round through the hub and writes `<round>/results.json` and `<round>/summary.md` (definitions in its docstring) |
| `relay_peer.py` | Records the peer relay a peer-dependent agent reads (`<round>/relayed/<task>.json`: the delivered payload, its document id and the relay status only) and the router's record of it (`<round>/router/<task>.json`: the plan, the request, the peer's receipt and the relay receipt; no agent reads it) |
| `list_claims.py` | Lists the claims of an answer as transmitted; with `--json`, each claim text's digest and the synthesis format the combinator writes (`synthesis_format`: the combinator sub-project's exported instructions, checked against the synthesis contract; `--instructions <dir>` reads a given export, which must be this repository's combinator release unless `--allow-other-release`) |
| `stem_mutations.py` | The STEM fault injections (STEM subjects only) |
| `stress_arena.py` | Replays a round under load (`docs/STRESS_RESULTS.md`) |
| `bind_adjudications.py` | Binds an adjudicator's judgments of translation fidelity to the recorded translations they judged |
| `test_arena_rules.py` | Regression tests of the functional rule and the reporting (run by path, below) |

A round directory holds `specialists/*.json` (the answers), and optionally `translations/*.json` (recorded translations,
with `claim_text_sha256` binding each to the claim text it was produced for), `syntheses/*.json`, `relayed/*.json`,
`router/*.json`, `tasks.json` and `adjudications/translation_fidelity.json`.

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
`list_claims.py` prints it, rendered by the sub-project's own code in its own isolated process:

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
not part of what the runner shows its agent. The agent writes the output object to `<round>/syntheses/<task_id>.json`:

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
round or leaves the record without a receipt.

```
python scripts/arena/run_arena.py <round>                           # results.json, summary.md; exit 0
python scripts/arena/run_arena.py <round> --fail-on-qualification   # exit 1 when the run is qualified (below)
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

The harness's injected verifier keeps the two-argument signature `fn(claim, report)`, so a replay translates on the same
path as the recorded rounds: task-authority premises are validated against the supplied texts only, and the rest stay
unvalidated (listed as unverified dependencies). Passing the task record (`fn(claim, report, task=...)`, which the
channel supports) validates them against the router's question too; it changes what a replay measures (round 7's
recorded fixtures carry 338 grounding records of a task-authority kind, 174 of them on premises), so it is a methodology
change for a new round, not for a replay.

## Injections no finding names

An injection no finding of its code names on the injected claim is a miss: a failure of the transport measure, listed
under `failures` with its reason. No rule takes a miss out of the count, whatever the cause. When the receipt itself names
the injected claim of a STEM mutation undecided (an ST-UNDEC finding: a relation outside the encodings, or a symbol with
no stated value), the failure reason quotes that finding and the record carries it as `undecided_on_injected_claims`, so
a miss that a limit of the encodings leaves reads as one; it is still a miss.

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
  id carries in this run;
- `ADJUDICATIONS_NOT_APPLIED`: adjudications that do not apply to this run (their translation was not served, or a digest
  differs).

With `--fail-on-qualification` a qualified run exits with status 1. Use it for a translation-regression run: it fails
instead of reporting figures for a different set of translations. Re-record the translations (with `claim_text_sha256`,
from `list_claims.py --json`) and re-adjudicate them when extraction changes; never re-key them by bare claim id.

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

After the round's records are complete, `run_arena.py` runs the delivery policy (`docs/DELIVERY.md`) over every genuine
answer, on a hub of its own carrying a transfer auditor. The pass replays each group's genuine traffic in order and opens
a delivery session per answer. It adds no record and moves no transport count. Its hub and claim verifier are bound at
import, so a harness that replaces `RouterHub` or `verify_claim` never reaches it. The contained harness switches it off
(`DELIVERY_PASS = False`) while it replaces them; `deliveries` then says it was not run. results.json carries
`deliveries`:

- the count per mode;
- per task: the mode, the label, the time to decision, the translation and overseer times, the formal path's reasons
  and claims, every candidate with its accuracy and whether it was chosen, the chosen answer, the signed receipt's id
  and whether it verifies, and whether the pass's receipt equals the genuine record's (status and codes);
- the pass's errors and its wall time.

summary.md has a "Delivery decisions" table with one row per task. The command line configures no overseer agent,
because the harness calls no model, and a replay calls no fidelity reviewer. So no formal path completes, and an answer
is withheld with its reasons. `run_round(round_dir, delivery_overseer={"pack": ..., "provider_factory": ...})` configures
overseer agents (tests only: scripted providers).

## Tests

```
python -I -m pytest -q scripts/arena/test_arena_rules.py   # the functional rule and its reporting, and what a peer relay file may hold
python -m pytest -q tests/e2e/test_arena_measures.py        # the separate measures, qualification, adjudications (default suite)
python -m pytest -q tests/e2e/test_arena_deliveries.py      # the delivery decisions in results.json and summary.md (default suite)
python -m pytest -q tests/stem/test_arena_stem_mutations.py # the STEM injections (default suite)
python -m pytest -q tests/stem/test_e2e_run1_detection.py   # the e2e run1 injections: all six named, each as the harness injects it
```
