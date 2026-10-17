# Arena harness

The arena replays real specialist answers through the hub exactly as production would carry them, adds injected faults,
and reports what the hub did. The per-round record is `docs/ARENA_RESULTS.md`.

| File | What it does |
| --- | --- |
| `run_arena.py` | Feeds one round through the hub and writes `<round>/results.json` and `<round>/summary.md` (definitions in its docstring) |
| `relay_peer.py` | Records the peer relay a peer-dependent agent reads (`<round>/relayed/<task>.json`) |
| `list_claims.py` | Lists the claims of an answer as transmitted; with `--json`, each claim text's digest |
| `stem_mutations.py` | The STEM fault injections (STEM subjects only) |
| `stress_arena.py` | Replays a round under load (`docs/STRESS_RESULTS.md`) |
| `bind_adjudications.py` | Binds an adjudicator's judgments of translation fidelity to the recorded translations they judged |
| `test_arena_rules.py` | Regression tests of the functional rule and the reporting (run by path, below) |

A round directory holds `specialists/*.json` (the answers), and optionally `translations/*.json` (recorded translations,
with `claim_text_sha256` binding each to the claim text it was produced for), `syntheses/*.json`, `relayed/*.json`,
`tasks.json` and `adjudications/translation_fidelity.json`.

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
| Transport (`metrics.transport`; the headline functional count) | Transmissions the hub delivered and decided: genuine traffic (genuine replies, peer relays, syntheses) delivered, injected faults named by a finding of the expected code on the injected claim, no INTERNAL_ERROR. Injections reported not applicable (below) are outside it, counted apart (`injected_faults.not_applicable`) | Whether a finding is true, whether a translation is faithful, whether an answer is better |
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

## Injections that are not applicable

A STEM injection no finding names is a miss unless two things hold, and only then is the record NOT APPLICABLE
(`not_applicable`, `not_applicable_reason`):

1. The harness's own reading of the answer (`stem_mutations.not_applicable`, independent of the front end under test)
   finds the changed figure in an expression that holds a symbol no statement of the answer or the request gives a
   value: for a slip, the computed side of the changed relation; for a substitution, the stretch that holds the figure.
   An identity such as `P(t + 4) = P₀e^(k(t + 1))` (the function P) or an equation in an unknown such as
   `18 000 = M × …` qualifies. A written calculation never does, whether of figures or of symbols with a stated value
   (`low = mid + 4` with `mid = 1` stated, `800 = 1600 e^(−5k)` with k stated), and whether or not a value is stated
   beside it.
2. The change moved none of the receipt's formal checks: each holds, fails or stays undecided as on the genuine
   receipt of the same answer (`run_arena.moved_checks`). A change that moved one is a miss when unnamed.

A not-applicable record is neither functional nor a failure. It is outside the transmissions of the transport measure
and is listed with its reason in results.json (`not_applicable_injections`) and in summary.md; the reason also quotes
the receipt's own ST-UNDEC finding on the injected claim. A named injection is a detection whatever this reading says,
and a record whose hub transport failed is a failure whatever its applicability.

A figure written as the exponent of a power of ten (or of e-notation, `6.31e-9`) changes in its first decimal digit
(`10^(−8.2)` → `10^(−8.5)`), never by a whole number. A whole-number change would alter the power by an exact power of ten, the factor of a unit
prefix, which the SI reading of a stated unit absorbs. The marker leaves a part label out ("(b) "), as every claim does.

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

## Tests

```
python -I -m pytest -q scripts/arena/test_arena_rules.py   # the functional rule and its reporting
python -m pytest -q tests/e2e/test_arena_measures.py        # the separate measures, qualification, adjudications (default suite)
python -m pytest -q tests/stem/test_arena_stem_mutations.py # the STEM injections (default suite)
python -m pytest -q tests/stem/test_e2e_run1_detection.py   # the e2e run1 injections: named, or not applicable with the reason
```
