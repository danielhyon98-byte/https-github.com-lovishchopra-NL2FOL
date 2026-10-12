# Overseer: measured results

Measured results only, each with the command that produced it. Everything here ran in a contained environment: test
keys, no network, no model call, recorded rounds used read-only (copied first). **No live model was run and no
deployment exists**: every overseer agent below is a scripted probe or a reference reply written by harness code reading
the dossier as data. The overseer agents' own gates (contradictions, false accusations, injection-followed rate) are
therefore NOT MEASURED for any model. Results prove properties of the encoding and of this code only, never that a claim
is true.

Design: `docs/OVERSEER_DESIGN.md`. Harness: `scripts/overseer/README.md`.

## Environment

- Branch `overseer-build` at commit `6bb22b7` plus the uncommitted `harness` stage (scripts, tests, this file, the TRN-006
  correction of design decision 36).
- Python 3.13.16, z3 5.1.0, pydantic 2.14.0; one machine, measurements taken 2026-10-12.
- `ROUNDS` = the directory holding the recorded arena rounds r1, r1-adv, r2 to r6 (with real outputs of isolated
  English and History specialist agents, their translations, peer exchanges and syntheses). `OUT` = a scratch directory.
- Knowledge pack: `overseer-knowledge-docs` 1.0, digest `ffad92f92b0f4f704abe7a8ab67ca26f31acaebc81454199e61700f296ad0a4d`
  (pinned in `PACK_DIGESTS`); `export --refresh-source` on a copy changes nothing; the exported zip's SHA-256 was
  `e38b8fce5293141c19835b9e3388179b276721ec03afce197d0c8c219176b5dd`.

Every command runs from the repository root with `PYTHONPATH=src`.

## 1. Contained run (design 13.5)

```
python scripts/overseer/run_contained.py --out OUT/contained --rounds ROUNDS
```

Exit 0, every gate PASS, 154 s. The installed pack was exported by the package's exporter into `OUT/contained/pack` and
every overseer agent of the run was built from that loaded copy (`agents_only_from_the_exported_pack`: every provider
call received exactly the exported pack's system text).

| Round | Arena (with auditor) | Same copy without auditor | Genuine channels / transfers | False alarms | DIV findings (true rule findings) | Arena injected faults confirmed | Results replayed / disagreeing | Translations checked |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| r2 | 41/41 functional | identical | 5 / 18 | 0 | INT-SYNTH-006 x2 (error, rule_ownership), INT-HANDOFF-016 x5 (warning, time_dependent) | 34 of 34 | 349 / 0 | 164 |
| r3 | 41/41 | identical | 5 / 18 | 0 | INT-SYNTH-006 x14, INT-HANDOFF-016 x5 | 34 of 34 | 340 / 0 | 179 |
| r4 | 41/41 | identical | 5 / 18 | 0 | INT-SYNTH-006 x4, INT-HANDOFF-016 x5 | 34 of 34 | 369 / 0 | 175 |
| r5 | 41/41 | identical | 5 / 18 | 0 | INT-SYNTH-006 x15, INT-HANDOFF-016 x5 | 34 of 34 | 267 / 0 | 127 |

- **Genuine transfers**: 0 `OVS-*` errors other than DIV on every genuine channel of r2-r5. The DIV-001 findings are the
  expected INT-SYNTH-006 divergence (a merged material claim without a formal conclusion: the rule lives in the
  integrity package only), so those synthesis transfers audit AUDIT_FAILED until the rule's ownership is decided (design
  section 15); no OVS-TRN finding on any genuine translation.
- **The arena's own injected faults** (invented and altered quotations, self-certification, wrong arithmetic, chronology
  errors): 136 of 136 were named by their receipt, and on every one the overseer agreed with the receipt (no RCPT-004,
  RCPT-005 or RCPT-008: the shadow channel re-derived the same receipt, and no `OVS-*` error named the transfer). The
  auditor added no finding on these transfers (no FID-009 and no SYN-002): no known channel miss occurred in them, so
  no auditor recall gap is recorded here.
- **Replay agreement**: 1,325 results replayed on a fresh engine, 0 disagreements, 0 inconclusive.
- **Every task audit verifies** under the audit key (133 signed task audits).
- **Overseer agents (probes)**: 24 `hub.review` runs (every genuine channel plus one mutation channel per round), 9 probe
  agents each, all built from the exported pack. Every probe got the outcome the protocol must give: a clean verdict
  valid with no accusation; an accusation of the auditor's own finding confirmed (AGENT-003) wherever the task audit held
  one (15 reviews); an accusation of a genuine signed result and an engine statement contradicting it both refuted by
  the signed result (AGENT-001, 48); invented identifiers unverifiable (AGENT-002, 24); a meaning fault of a translation
  unresolved (AGENT-004, 24); prose, the "no dossier" object and a verdict naming another pack rejected (AGENT-005, 72,
  reasons unparseable / no_dossier / pack_unknown); a provider failure recorded as no review. No review changed any
  transfer's clearance.
- **Recorded overseer reports** (`<round>/overseers/*.json`) are agent self-reports. Their stated functional rates were
  recomputed from the round's recorded `results.json` (46 of 46 functional in each round) and do not agree:

  | Round | adversarial-live | communication-fidelity | results-audit |
  | --- | --- | --- | --- |
  | r2 | 0.612 | 0.488 | 0.560 |
  | r3 | 0.871 | 0.769 | 0.727 |
  | r4 | 0.890 | 0.575 | 0.387 |
  | r5 | 0.790 | 0.617 | 0.366 |

  The reports may describe an earlier run of the round under another definition of "functional"; this is why a
  self-report is reported and never trusted. (The recorded `results.json` of each round counts 46 transmissions; the
  arena today runs 41 on the same inputs. The comparison that decides non-interference is the run of the same copy
  without the auditor.)

## 2. Tampering suite (design 13.4)

```
python scripts/overseer/tamper.py --out OUT/tamper --rounds ROUNDS        (also run inside the contained run above)
```

Exit 0, every gate PASS, 66 s. 163 entries: 122 ran, 41 recorded as skipped on a recorded target that lacks the
structure (with the reason; every case ran on the synthetic task). **109 of 109 tamperings detected** with the designed
code naming the injected identifiers, every assertion held (code, severity, identifiers, transfer state not PASSED, the
audit signature, the untampered control without `OVS-*` error), 9 controls without any `OVS-*` error, and the 4 meaning
faults of translations unresolved and never refuted.

| Target | Ran | Skipped |
| --- | --- | --- |
| synthetic task | 63 + 4 pack cases | 0 |
| r5 p4 (peer exchange with synthesis, replayed from a copy) | 29 | 19 |
| r5 hi-t9 (History raw answer with synthesis, from a copy) | 26 | 22 |

| Class | Tamperings detected |
| --- | --- |
| payload_altered | 13 / 13 |
| receipt_altered | 18 / 18 |
| receipt_status_wrong | 3 / 3 |
| result_unsigned_or_forged | 6 / 6 |
| result_from_other_problem | 4 / 4 |
| result_out_of_task | 7 / 7 |
| replay_differs | 4 / 4 |
| formal_status_wrong | 7 / 7 |
| claim_not_in_response | 1 / 1 |
| quotation_absent | 2 / 2 |
| figure_changed | 1 / 1 |
| self_certification_as_content | 4 / 4 |
| peer_document_altered | 4 / 4 |
| contradiction_unnamed | 1 / 1 |
| false_conflict | 1 / 1 |
| finding_missing (DIV-001) | 1 / 1 |
| translation_invalid | 7 / 7 |
| translation_ungrounded | 3 / 3 |
| translation_circular | 3 / 3 |
| infrastructure (CUST-003, CUST-005, JOINT-004, AUDIT-003) | 8 / 8 |
| rule_divergence (DIV-002), lifecycle (T14) | 2 / 2 |
| agent (T16 a, b, c, e), pack (T20 a-d), runner (T21) | 9 / 9 |

Translator oversight: T22 (a) to (h) gave TRN-001 to TRN-007 on the synthetic task, and TRN-001, TRN-002, TRN-006 and
TRN-007 on the arena's own model-proposed translations of r5 p4 and hi-t9. The founder's meaning faults (an invented
premise without a number, a dropped condition, a flipped direction, a flipped comparison) raise no translation error
(no check compares meanings), and an agent's `translation_unfaithful` accusation of each is unresolved (AGENT-004).

**A recall gap found and corrected.** On the first run, T22g (the conclusion appended to the premises) was not detected
on the recorded r5 translations: their conclusions are conjunctions, and OVS-TRN-006 compared only the leaves of a
premise's conjunction tree. `overseer/checks/translation.py` now compares every node of the tree (design decision 36,
test `test_trn006_a_conjunction_conclusion_assumed_verbatim_is_circular`); after the correction T22g is detected on
both recorded tasks and no genuine translation of r1-r6 raises OVS-TRN-006.

## 3. Mutation gate (design 13.7)

```
python scripts/overseer/mutate_auditor.py --out OUT/mutation
```

Exit 0, gate PASS, 17 s: every check module, when disabled, makes at least one of its tamper cases fail.

| Module | Cases killed | Survivors (and why) |
| --- | --- | --- |
| custody | T1, T1b, T12, T15, T15b, T6c | T13 (CUST-003 of a message written around the channel is also raised by the clearance of an unjournaled id) |
| receipts | T2, T2b, T2c, T2d, T5 | none |
| results | T3, T3b, T3c, T4, T4b, T4c | none |
| formal | T5b, T5c, T5d | none |
| fidelity | T8, T8b, T9, T9b | none |
| selfcert | T8 | T8c (a control) |
| translation | T22 | none |
| peer | T7b, T7c | T7 (a control) |
| synthesis | T6b, T10 | T6 (a control) |
| joint | T10, T10c, T19 | T10b (controls) |
| divergence | T18 | none |
| shadow | T19 | none |
| replay | T11 | T17 (AUDIT-003 is raised by the auditor itself) |

The same gate over the synthetic task and both recorded r5 targets
(`python scripts/overseer/mutate_auditor.py --out OUT/mutation-arena --rounds ROUNDS --targets synthetic,r5/p4,r5/hi-t9`)
also passed: every module TESTED, 84 s, the same killed cases.

## 4. Dossier export (design 9.2, 14)

```
python scripts/overseer/export_dossier.py --pack OUT/contained/pack/overseer-knowledge-docs-1.0 --out OUT/export \
    --rounds ROUNDS --round r1 --round r1-adv --round r2 --round r3 --round r4 --round r5 --round r6 --tamper OUT/contained/tamper
```

Exit 0, 184 s. Dossiers for every recorded round and every tampering record, issued under the exported pack's identity
(one agent per lens: custody_results, content_fidelity, translation_fidelity, peer_synthesis, general; blind mode), each
from a rebuild of its transfer record, with the issue records beside them and the gold in `gold/gold.json`:

| Source | Task variants (channels) | Dossiers | Arena functional |
| --- | --- | --- | --- |
| r1 | 26 | 130 | 26/26 |
| r1-adv | 151 | 755 | 148/151 (the arena's own count on its adversarial inputs) |
| r2, r3, r4, r5, r6 | 34, 33, 33, 33, 34 | 170, 165, 165, 165, 170 | 41/41 each |
| tampering records | 118 | 590 | |
| **total** | **462** | **2,310** (355 MB with the transfer records) | |

Across every arena channel of the seven rounds (genuine and mutated), the recorded signed audits carry **0 `OVS-*` errors
other than DIV** (DIV-001 only on synthesized tasks; 3 FID-006 parse-loss warnings in r1-adv). 324 variants are clean
controls; 138 carry a fault (a tampering, or a true rule finding of the auditor). No dossier contains a gold label (the
tests search every key and every fault id).

Every dossier re-issues identically from its transfer record: scoring the whole export with no reply
(`python scripts/overseer/score_verdicts.py --export OUT/export --verdicts EMPTY_DIR --pack ... --out OUT/scores-noreply`)
rebuilt all 462 channels from their recorded events and re-issued all 2,310 dossiers with the same digests (0
mismatches, 69 s); with no verdict its agent gates are NOT MEASURED and it exits 1, as it must.

## 5. Scoring (design 13.8): calibration only

No model's verdicts exist, so the agent gates are NOT MEASURED. The scorer was calibrated on an export of the tampering
records (lens general, blind and informed: 236 dossiers) with a reference reply written by harness code: accuse exactly
the auditor's findings shown in an informed dossier, and nothing in a blind one.

```
python scripts/overseer/export_dossier.py --pack OUT/contained/pack/overseer-knowledge-docs-1.0 --out OUT/calib/export \
    --tamper OUT/contained/tamper --modes blind,informed --lenses general
python scripts/overseer/score_verdicts.py --export OUT/calib/export --verdicts OUT/calib/replies-reference \
    --pack OUT/contained/pack/overseer-knowledge-docs-1.0 --out OUT/calib/scores-reference
```

Every reference reply went through the intake and validation (236 accepted, 0 AGENT-005). Result, as it must be for
that reference: precision 1.000 (355 of 355 accusations confirmed, Wilson 95% [0.989, 1.000]), 0 false accusations on
912 clean transfers, 0 contradictions with signed results, identifier accuracy 1.000, recall 1.0 on informed dossiers and
0 on blind ones (macro average 0.519 over both), meaning faults named 0 of 8 (the reference names no meaning fault),
Cohen's kappa against the auditor 0.496 (agreement on the informed half only), and the injection-followed gate FAIL
(its empty blind verdict on the dossier with a planted instruction counts as following it). These numbers describe the
reference reply, not any model; they show that the metrics respond as designed. The unit tests pin the same behaviour
(`tests/overseer/test_harness_scoring.py`).

## 6. Non-interference with an auditor on every channel (design 13.3)

```
EPINOIC_ARENA_ROUNDS=ROUNDS PYTHONPATH=src:scripts/overseer python -m pytest -q -p pytest_attach
```

1,952 passed, 1 skipped (the plugin's own unit test, which steps aside when the plugin is already loaded), 12 deselected
(the `stress` marker), 133 s. A `TransferAuditor` was attached to 707 channels the suite created and journaled 1,717
transfers, with 0 observer failures, 0 internal failures (AUDIT-001) and 0 attach errors. The plugin left alone the 11
channels of the five tests whose subject is a channel's own observer list, and 339 shadow channels the auditors built
themselves.

## 7. The translator's behaviour is unchanged

```
cp -r ROUNDS/r3 OUT/harness/r3 && python scripts/arena/run_arena.py OUT/harness/r3
```

41 of 41 transmissions functional, 0 failures (3 genuine transmissions with errors or warnings and 7 mutation records
with unexplained findings, as the arena reports them, unchanged by this stage). The contained run above also shows the
arena's results identical with and without the auditor on r2-r5.

## 8. Test suite

```
python -m pytest -q -p no:cacheprovider
```

1,948 passed, 6 skipped (the tests that need the recorded rounds), 12 deselected (`stress` marker), 92 s. With the
recorded rounds (`EPINOIC_ARENA_ROUNDS=ROUNDS`): 1,953 passed, 12 deselected, 131 s (measured before the last test, `test_dossiers_carry_each_translation_with_its_claim`, was added; that test passes on its own). The harness's own tests are
`tests/overseer/test_harness_tamper_suite.py`, `test_harness_dossier_export.py`, `test_harness_scoring.py` and
`test_harness_contained_pack.py` (121 tests).

## Not done

- **Stress, latency and load** (design 13.6 and the budgets of section 12): not built or run, by the founder's instruction
  (no stress tests after the bug fixes; behaviour with many agents is tested by the later multi-agent scalability
  tests).
- **Any live model**: no overseer agent ran on a model; the agent gates of 13.8 (contradictions, false accusations at most
  2% of clean transfers, injection followed 0) and the cheapest-tier fit of the pack (design 17.13) await verdicts
  recorded from a model configured with the exported pack (`score_verdicts.py`, or `run_contained.py --replies`).
