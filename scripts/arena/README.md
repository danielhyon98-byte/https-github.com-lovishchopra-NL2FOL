# Arena harness

The arena replays real specialist answers through the hub exactly as production would carry them, adds injected faults,
and reports what the hub did. The per-round record is `docs/ARENA_RESULTS.md`.

| File | What it does |
| --- | --- |
| `run_arena.py` | Feeds one round through the hub and writes `<round>/results.json` and `<round>/summary.md` (definitions in its docstring) |
| `relay_peer.py` | Records the peer relay a peer-dependent agent reads (`<round>/relayed/<task>.json`: the delivered payload only) and the router's record of it (`<round>/relayed/<task>.router.json`: the peer's receipt with every finding, the relay record; never part of a specialist's bundle) |
| `list_claims.py` | Lists the claims of an answer as transmitted; with `--json`, each claim text's digest and the synthesis format the combinator writes (`synthesis_format`, built from the synthesis contract) |
| `stem_mutations.py` | The STEM fault injections (STEM subjects only) |
| `stress_arena.py` | Replays a round under load (`docs/STRESS_RESULTS.md`) |
| `bind_adjudications.py` | Binds an adjudicator's judgments of translation fidelity to the recorded translations they judged |
| `test_arena_rules.py` | Regression tests of the functional rule and the reporting (run by path, below) |

A round directory holds `specialists/*.json` (the answers), and optionally `translations/*.json` (recorded translations,
with `claim_text_sha256` binding each to the claim text it was produced for), `syntheses/*.json`, `relayed/*.json`,
`tasks.json` and `adjudications/translation_fidelity.json`.

## Synthesis format (the combinator's instructions)

The combinator writes `<round>/syntheses/<task_id>.json` for each report it synthesizes:

```
{"report_id": "<the report_id list_claims.py prints>",
 "claims": [{"text": "...", "source_claim_ids": ["..."], "certainty": "established" | "probable" | "possible",
             "transformation": "carried" | "paraphrased" | "merged" | "narrowed" | "generalized"}],   (2 to 4)
 "dropped": [{"source_claim_ids": ["..."], "reason": "..."}],
 "conflicts": [{"conflict_id": "...", "claim_ids": ["...", "..."], "description": "...", "status": "unresolved" | "resolved_with_basis", "basis": "..."}]}
```

- `conflicts` (optional) discloses a disagreement between the sources: `claim_ids` are the source claim ids, and a
  `resolved_with_basis` record needs a meaningful `basis` (INT-CONFLICT-003). The records are relayed as written (with
  several reports in a group, each `conflict_id` is qualified by its task id), so a disclosed conflict reaches the hub.

- `transformation` is exactly one of those five words, a category of what was done to the cited sources, never a
  description of the edit: `carried` (one source, its text unchanged), `paraphrased` (one source reworded),
  `merged` (several sources combined), `narrowed` (part of a source left out on purpose), `generalized` (sources stated
  more generally). What each records and how the ledger reads it is `TRANSFORMATION_MEANINGS` in
  `src/epinoic_logic/integrity/contracts.py`; `list_claims.py --json` prints the same text as `synthesis_format`, and its
  plain output ends with the list, so the instructions come from the contract and cannot drift from it.
- `certainty` is never stronger than the weakest cited source (INT-LEDGER-003); figures, units, dates and quotations
  are kept exactly as the source states them; a material claim left out goes in `dropped` with a meaningful reason.
- Any other value (free text, an alias such as "joined", another spelling) is refused by the hub: the synthesis is
  REJECTED with INT-REQ-009 and INT-SYNTH-014 naming each claim, and it is not delivered. So is a file that is not JSON,
  a claim that is not an object, a missing field or a field the synthesis contract does not have. A field the syntheses
  format above does not hold (at the file level, in a claim, in a dropped entry or in a conflict record: a
  self-certifying `verified`, a `materiality`) is carried to the hub as written, so the hub refuses the synthesis, and the
  synthesis record names it (`unknown_synthesis_fields`) and is not functional: it is refused, never dropped silently.

A workflow that briefs a combinator agent should give it these instructions, or tell it to read `synthesis_format` from
`list_claims.py --json`. The end-to-end simulation of 16 October 2026 named the field without its values, and its
combinator wrote free text in all 62 synthesized claims; the recorded rounds r1 to r7, whose combinator was told the
values, carry one of them in all 202.

`run_arena.py` relays each group's synthesis to the hub as the JSON the router receives (`group_synthesis` passes the
combinator's fields on as written; it never builds the contract models itself), so the hub's contract validation decides
it. A malformed synthesis is a REJECTED receipt recorded with its findings, and, being genuine traffic that was not
delivered, a failed synthesis record whose `failure_reasons` name the codes; it is never an exception that stops the
round or leaves the record without a receipt.

A peer-dependent agent is given `relayed/<task>.json` and nothing else of its peer: the specialist_report/1.0 payload as
the hub delivered it, with the peer document id it is supplied under. The receipt of that delivery (the hub's findings,
which are the router's to weigh and may be false) is written to `relayed/<task>.router.json` and is never put in a
specialist's bundle (E2E B3: a specialist that was shown a false formal-check finding repeated it to the student; the
channel now names an answer that hands a system check result to the reader as INT-REQ-017).

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
open a figure no source asserts, which the question may leave open on purpose). Neither count changes the transport
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
It is withdrawn: the injection is the base one, and the checks name it at its cause (`docs/STEM_DESIGN.md`, section 21,
items 1 and 7, and 21.3). The marker leaves a part label out ("(b) "), as every claim does.

## Qualified runs

A run is qualified when its translation figures cannot stand for the recorded round's. The summary's title says so, and
results.json carries `qualified` and `qualifications`:

- `TRANSLATIONS_LOST`: recorded translations were not served (for example, claim ids changed after the parser changed);
  a translation recorded under a bare claim id is served to the agent-qualified id the parsers give the same claim on a
  task with two or more agents (`<id>@<agent>`, end-to-end B17), with its problem naming that id (`fixture_claim_ids`,
  `fixture_for_claim`; repair round 2), so the qualification alone loses nothing;
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

## Tests

```
python -I -m pytest -q scripts/arena/test_arena_rules.py   # the functional rule and its reporting
python -m pytest -q tests/e2e/test_arena_measures.py        # the separate measures, qualification, adjudications (default suite)
python -m pytest -q tests/stem/test_arena_stem_mutations.py # the STEM injections (default suite)
python -m pytest -q tests/stem/test_e2e_run1_detection.py   # the e2e run1 injections: all six named, each as the harness injects it
```
