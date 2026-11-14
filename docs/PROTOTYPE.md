# The integrated prototype after arena round 8

> Paths and commands below follow the overseer sub-project's layout (architecture step 2 of phase 2: the Overseer is
> `overseer/`, package `epinoic_overseer`); the figures are as measured.

For Bruno. This page describes the integrated prototype as it stands after arena round 8 (the integrated round `c1`)
and the fixes of its clearance. Three commits carry that clearance:

- `f2329df` holds its fixes. The independent push check held this commit, so it was never uploaded on its own.
- `32a5c0e` is the follow-up. It narrows the note rule that the push check held `f2329df` on, and it withholds the
  FORMALLY CHECKED label for every answer (rule `formal-label-withheld`).
- `5060a52` fixes three regressions of those fixes that the publisher's simulation of `32a5c0e` found (section 4).

The architecture step after round 8 is on this tree too (`ab44c8a`, `b570339`, `f3d338a`, `c4f276c`). The page says so
where it changes a command or a figure. Every figure below names the commit it was measured on. Every figure is a
measured result taken from the repository's own records (`tests/README.md`, `docs/ARENA_RESULTS.md`, `docs/STEM_RESULTS.md`,
`docs/OVERSEER_RESULTS.md`, `docs/DELIVERY.md`, the commit messages they cite), from the round's harness summary and
overseer reports, or from a replay of the round on this tree; each says which. Nothing here is deployed, and no live
model provider was called by any test, replay or harness run reported here.

**Scope.** Results prove properties of the encoded problems only. An ENTAILED verdict shows that the encoded conclusion
follows from the encoded premises under this configuration; it does not show that a premise is true, that a translation
is faithful or that an answer is right. A STEM check shows that the written arithmetic, step, conversion or balance holds
or does not under the stated readings, never that a law applies. A specialist's or an overseer agent's own report is
advisory: only a signed engine result or a deterministic re-check confirms anything. Non-success statuses are never
shown as success.

## 1. What the prototype is

The prototype is code, not an agent. Its traffic is the work of agents: a router, sixteen subject specialists and a
combinator. Every message between them crosses one hub, where it is translated into logic the Z3 engine decides, so
that no miscommunication passes from one agent to the next unnamed. It has five parts.

1. **The logic translator and the Z3 engine** (`src/epinoic_logic/translate/`, `engine/`, `channel/`, `branches/`,
   `integrity/`). Each specialist's answer is parsed into claims. Deterministic code decides which claims may be
   formalised. A translation provider proposes a small typed problem for each eligible claim (IR 1.0). That proposal is
   data: it is parsed strictly, validated against a closed schema and never executed. The engine checks consistency
   before entailment, signs every result (HMAC) and lists every premise the proof relied on that no check established.
   The release assessment is a separate record from the formal status. Versions on this tree (`epinoic-logic version`):
   engine 0.4.0, policy 2026.10-v4, translator 0.4.0, IR 1.0, z3 5.1.0.
2. **STEM support** (`src/epinoic_logic/stem/`, the `sciences`, `mathematics` and `computer_science` branches). A
   front end reads answers that mix equations and prose in LaTeX, Unicode, ASCII and words, and evaluates no text. It
   turns each relation it recognises into an IR problem the engine decides: written arithmetic, substitutions, unit
   conversions, algebra steps, stated roots, balances, Boolean identities and based numerals. Any other relation it
   names undecided, with the reason. A wrong step reaches the router as an INT-SUBJ-001 error naming the claim, with the
   computed and stated values (`docs/STEM_DESIGN.md`, `docs/STEM_RESULTS.md`).
3. **The logic-checking overseer** (`overseer/src/epinoic_overseer/`). It has two layers.
   - **The transfer auditor** is deterministic code. It journals every transfer in a hash-chained, HMAC'd journal. It
     re-runs every signed result the receipts cite. It checks that what the router received is what the specialist
     wrote, that each translation is faithful to its claim's words, numbers and quotations, and that a synthesis
     accounts for its sources. The router acts on a transfer only when the auditor's clearance allows it
     (`policy.may_act`).
   - **The overseer agents** are model-based reviewers. They are built only from the package's code and an exportable,
     versioned knowledge pack. The installed pack is `overseer-knowledge-docs` 2.1 (the architecture step added 2.0 and
     2.1); round 8 ran with 1.4, and its clearance installed 1.5. Each of them stays pinned beside 2.1. Each agent gets
     a dossier and returns a verdict, which is validated against the journal and the
     signed results. A verdict is advisory: only an accusation that a deterministic check confirms reaches the router,
     and no agent changes a clearance.
4. **Consolidation and the self-duplicating overseer pool.** When several agents answer one input (duplicated instances
   of one specialist, or several specialists), `hub.consolidate` returns one signed consolidated response:
   - equivalent answers are grouped deterministically;
   - every answer with an error-level finding or a repeated fault (`OVS-REP-001`) is excluded;
   - conflicts between groups are disclosed, not resolved by choosing.

   `hub.review_pool` sizes the overseer agents deterministically. It starts one instance by default and adds more over
   a per-instance quota or when faults repeat, never past a maximum (four by default). Every instance comes from the
   same exported pack. Since architecture step 2c that sizing is the flash router's decision (`flash-router/`, a
   separate agent attached through the router port), held to the overseer's own minimum-oversight floor: a plan below
   it is refused and the floor plan runs, and with no router attached the floor plan runs.
5. **The delivery policy** (`overseer.delivery_policy`, `delivery-v1`, `docs/DELIVERY.md`). This is the founder's
   four-minute rule. An answer can be delivered FORMALLY CHECKED only when, within the 240 s translation budget, every
   material eligible claim was translated, decided positively, passed the release rule and was cleared by the transfer
   audit, every claim of the answer carries a positive outcome of a signed engine result, and the receipt names no
   unchecked working and no agent self-report. Otherwise the fallback runs: overseer
   agents built from the exported pack score every candidate answer. The most accurate acceptable candidate is
   delivered OVERSEER-SELECTED only when its accuracy is strictly above 0.90, compared as an exact fraction. Otherwise
   the answer is withheld. Every decision is recorded in a signed delivery receipt. Only FORMALLY CHECKED claims a
   check; every other label says "not formally checked, not verified".

   **In this release the FORMALLY CHECKED label is withheld for every answer** (rule `formal-label-withheld`,
   `docs/DELIVERY.md` condition 6d). Six attack rounds on the clearance fix showed that no reader of free text keeps
   every agent assurance away from the label, so the formal path never completes and every answer follows the
   fallback. The formal path's other conditions still run and name their reasons on the receipt. Round 9 designs a
   label policy that holds under attack before the label returns.

**Which tier runs which role.** Deployed agents run on the cheapest model tier: the specialists, the combinator, the
translation provider and the overseer agents. The checks every transfer depends on use no model. In testing, the
strongest tier does the checking: the arena's overseer lenses, the judges of the overseer agents and the fixers.

**The specialists of round 8.** From round 8 on, the specialists are built from the agent-training API connector
together with the v4 master prompts and knowledge bases. Round 8 used the connector at commit
`5b60229b6f08bea88f7cf28316282469942ce46d`.

## 2. Using it (commands checked on this tree)

All commands run from the repository root, in the installed environment. Each was run once on `f2329df`'s tree when
this page was first written, except the install and the full suite, whose figures come from the commit messages, and
the pack export, which was checked again on `f3d338a`'s tree.

**Install.**

```
python -m venv .venv && .venv/bin/pip install -e ".[dev,service,providers]"
```

For an integration-kit install, pin the solver the suite was measured with:
`pip install -c integration/constraints.txt -e ".[dev,service,providers]"`.

**Run the suite.**

```
python -m pytest -q -p no:cacheprovider
```

- Full runs, each recorded in the message of the commit it was measured on:

  | Commit | Passed | Failed | Skipped | Recorded rounds supplied | Time |
  | --- | --- | --- | --- | --- | --- |
  | `f2329df` | 18,395 | 0 | 12 | no | 55 min 55 s |
  | `32a5c0e` | 22,503 | 0 | 12 | no | 1 h 16 min 20 s |
  | `5060a52` | 22,721 | 0 | 0 | yes | 1 h 18 min 30 s |
  | `c4f276c` (the architecture fixes after round 8, the last commit before round 9) | 23,051, and 1 expected failure | 0 | 0 | yes | 1 h 32 min 17 s |

  Each run also deselected 45 tests. The 12 tests skipped at `f2329df` and `32a5c0e` need the recorded rounds, and
  neither run supplied them. Neither verification ran the overseer's contained run either, and that is how the three
  regressions that `5060a52` fixes stayed hidden.
- The 45 deselected are the stress tests. They are not run, by the founder's instruction: never use `-m stress` or
  `scripts/arena/stress_arena.py`.
- Without the recorded arena rounds, the tests that need them are skipped. To run them, set
  `EPINOIC_ARENA_ROUNDS=<directory holding the recorded rounds>`; the tests copy the rounds first and never write to
  them.
- For a quick check (measured on `f2329df`'s tree), the delivery policy and engine subset
  (`overseer/tests/overseer_tests/test_delivery_policy.py overseer/tests/overseer_tests/test_delivery_fallback.py tests/engine`) gave 1,114 passed in
  34 s.

**One verification from the command line.**

```
epinoic-logic verify problem.json        # IR 1.0 problem file; prints the signed result as JSON
epinoic-logic version                    # component versions
```

The transitivity example of `docs/integration-contract.md` section 8 gives `ENTAILED`.

**Run the service.**

```
export EPINOIC_SERVICE_TOKEN=<bearer token, at least 16 characters>
export EPINOIC_SIGNING_KEY=<hex, at least 16 bytes>
epinoic-logic serve --host 127.0.0.1 --port 8080
curl http://127.0.0.1:8080/healthz
curl -H "Authorization: Bearer $EPINOIC_SERVICE_TOKEN" -H "Content-Type: application/json" \
     --data '{"problem": { ...IR 1.0 problem... }}' http://127.0.0.1:8080/v1/verify
```

- `/healthz` answers with the component versions.
- `/v1/verify` takes the problem inside an envelope, `{"problem": ...}`, optionally with `config` and a named `policy`
  (`linear`, `nonlinear` or `joint`). It returns the signed result.
- The other routes are `/v1/results/verify-signature`, `/v1/results/release-check` and `/v1/outcomes`
  (`src/epinoic_logic/service/README.md`).
- Checked on `f2329df`'s tree with throwaway local values: `/healthz` gave 200, and `/v1/verify` gave `ENTAILED` with a
  signature.
- `EPINOIC_PROFILE=integration` serves the integration protocol's checks service instead (`integration/README.md`).

**Replay an arena round.** The recorded rounds are kept outside the repository and are read-only. Always replay a copy:

```
cp -r <recorded round> <copy>
python scripts/arena/run_arena.py <copy>                         # writes <copy>/results.json and <copy>/summary.md
python scripts/arena/run_arena.py <copy> --without-task-record   # the old replay configuration, for comparison
python scripts/arena/run_arena.py <copy> --fail-on-qualification
```

- `list_claims.py`, `relay_peer.py` and `bind_translations.py` record a new round. Their docstrings and
  `scripts/arena/README.md` give the steps.
- `bind_translations.py` records each translation's claim-text digest. That step is what lifts the FIXTURES_UNBOUND
  qualification described below.

**Export the overseer pack.**

```
python -m epinoic_overseer.export --out <dir> --zip     # writes <dir>/overseer-knowledge-docs-2.1/ and its zip
python -m epinoic_overseer.export --verify <dir>/overseer-knowledge-docs-2.1.zip
```

- The export writes the master prompt, nine numbered documents, a README for whoever deploys it, the dossier and
  verdict schemas, and a manifest.
- Checked on `f3d338a`'s tree: pack 2.1 (integration step 2: the review of a specialist's revision request, beside architecture step
  3's twofold review of a combined answer), digest `a60727fce80a4190f59a8a0e21bf0c69cb759bab4a04876d81c88095ea21ebb5`,
  which is the digest pinned in `overseer/src/epinoic_overseer/pack.py` and in the service (`integration/overseer_port.py`).
  `--verify` on the zip returned `ok`. Pack 2.0 (`c2be21ab…`) and pack 1.5, the round-8 pack (`cac995dc…`), stay pinned
  beside it.
- The delivery policy loads the exported pack: `DeliveryPolicy(pack=load_pack(<zip>), provider_factory=...)`.

## 3. What round 8 measured

**Material.**
- 24 answers from the sixteen v4 specialist agents: sixteen single tasks, plus four peer pairs (two humanities pairs,
  one STEM pair and one STEM-humanities pair).
- 4 recorded peer relays and 20 combinator syntheses.
- 469 recorded translations.
- 155 injected-fault records, giving 203 transmissions in all.

The measures below are separate, and each has its own denominator. They are never combined into one headline.

### 3.1 The overseer lenses (each lens's own question)

Five independent lenses judged the round, each on its own question. Their rates come from each lens's report; the
first clearance commit, `f2329df`, records the five rates in its message. A lens rate is not a transport rate, although the
lens files name the field `infrastructure_functional_rate`.

| Lens | What it judges | Rate | Findings (major / minor) | Flagged critical by the lens | Earlier findings the lens re-checked: fixed / still open (as the lens reports) |
| --- | --- | --- | --- | --- | --- |
| results audit | receipts against their input, over the 203 records | 0.1921 | 41 (25 / 16) | 21 | 18 / 7 |
| communication fidelity | what the router received against what the specialist said | 0.3962 | 22 (15 / 7) | 4 | 12 / 6 |
| adversarial live | hostile variants written by the lens | 0.7561 | 25 (21 / 4) | 0 | 11 / 4 |
| STEM integration | the 95 records of the seven STEM subjects | 0.1474 | 37 (28 / 9) | 18 | first round of this lens |
| translation fidelity | the round's translations, judged claim by claim | 0.9424 | 22 (9 / 13) | 6 | 4 / 7 |

- The lenses reported 147 findings in all, 49 of them flagged critical. No lens reached 0.98.
- The lowest rates come from false error-level findings on correct work. The STEM lens counted 14 false INT-SUBJ-001 on
  five of the nine genuine STEM answers. The results audit found 13 of the 24 answers excluded from delivery by false
  error-level findings.

### 3.2 Transport (the harness's functional count)

Transport asks only whether the hub delivered and decided every transmission and named every injected fault. It does
not judge whether a finding is true, whether a translation is faithful or whether an answer is better.

| When | Functional transmissions | Source |
| --- | --- | --- |
| As recorded (the round's own run, 289.4 s) | 192 of 203 | `docs/OVERSEER_RESULTS.md` section 35, `docs/STEM_RESULTS.md` 10.15 |
| After the STEM fixes of the clearance, mid-clearance | 201 of 203 | same |
| At `f2329df` | 203 of 203 | its commit message; the replay on its tree (section 3.8) |
| At `32a5c0e` and at `5060a52` | 203 of 203 | each commit's message |
| At `c4f276c` (after the architecture step) | 203 of 203 | its commit message |

- Every recorded earlier round is unchanged at each of these four commits (each commit's message): r1 30/30, r1-adv
  150/151 (the planted empty answer stays rejected), r2 to r6 46/46 each, r7 177/177.
- The replay at `f2329df` puts no error-level finding on any of its 48 genuine replies, relays and syntheses. On the
  recorded run, the lenses named false errors (section 3.1).

### 3.3 Fixture coverage

- 451 of the 469 recorded translations are served. The other 18 belong to claims that are no longer eligible after
  the clearance's eligibility changes (TRANSLATIONS_LOST).
- All 451 are bound by claim id only (FIXTURES_UNBOUND). The round recorded no claim-text digests, and the recorded
  round is read-only.
- The briefing listings were kept for seven tasks. Bound with them by `bind_translations.py --listings` on a copy, 98
  fixtures carry their digest, 95 are served bound and none is refused as stale (`docs/ARENA_RESULTS.md`, "Round 8
  clearance"). Rounds from 9 on should record the digests.

### 3.4 Translation fidelity

- The translation-fidelity lens rated the round's translations, as they ran in the round, at 0.9424, with 22 findings.
- The harness itself has no adjudication file for round 8, so its fidelity measure reads "not adjudicated".
- This lens rate is not comparable with round 7's 0.6384: different material, a different translator tree and a
  different lens run.
- No live translator re-translated anything after the fixes, so fidelity on the current code is not measured.

### 3.5 Claim counts (genuine pass, replay at `f2329df`)

| Measure | Count |
| --- | --- |
| Claims extracted | 740 |
| Eligible for translation | 459 |
| Attempted | 451 |
| Completed (a definitive verdict displayed) | 199 |
| Approved (displayed ENTAILED, no error-level finding on the claim) | 199 |
| ...of which rest on at least one ungrounded premise | 175 |
| ...of which rest on at least one unresolved dependency | 195 |
| Release permitted by the release assessment | 0 |

- Translation outcomes on the genuine pass: ENTAILED 199, UNSUPPORTED 167, AMBIGUOUS_TRANSLATION 60,
  INVALID_FORMALIZATION 25 and NOT_ELIGIBLE 18.
- No definitive verdict other than ENTAILED is displayed on a genuine claim.
- 24 encodings get no verdict: vacuous (E108) 2, circular (E112) 6 and widened exact figures 16.
- A retry is not exercised for 23 genuine claims, because a recorded translation is one output and its retry gets that
  same output.
- "Approved" is a claim count. It is not a release decision, and it is not a fidelity judgement.

### 3.6 False approvals

What can be said from the measurements:

- **The delivery policy approved nothing.** All 24 answers were withheld (section 3.7), so no answer reached a student
  under a label it had not earned.
- **The policy had a defect, now fixed.** A Physics answer whose prose arithmetic was left unchecked (CORE-QNT-001), or
  whose dated order was left undecided (CORE-CHR-001), beside a clean calculation was delivered FORMALLY CHECKED by
  probe. The results audit reported this, and the clearance fixed it: such an answer is now withheld, with the reason
  naming the code and the claim (`docs/DELIVERY.md` 6a).
- **The engine displayed no false verdict on a genuine claim.** No definitive verdict other than ENTAILED was displayed
  on one. The release assessment permitted none of the 199 approved claims, so formal approval never stood as
  permission to release.
- **The overseer agents green-lit 17 transfers.** The results audit judged 11 of them inaccurate:
  - 7 carry injected faults that the receipts did name, so the infrastructure handled those transfers correctly.
  - 1 is within the documented 1% tolerance.
  - 1 holds only historical content errors, which the infrastructure does not claim to check.
  - 2 are infrastructure misses:
    - t33f4ed: Mathematics AA's wrong general term was named only ST-REF-002.
    - t99334c: Psychology's altered scenario quotation was named only CORE-SRC-003, and its unsupported link was not
      named.

  The judge's list in `tests/README.md` also records t3159a5. That answer told the student every claim was verified
  while its signed receipt was ACCEPTED_WITH_FINDINGS. The receipt named the fault, so the hub's status was not shown
  as success. The agents' green light on that transfer was a review error.
- **Five repeated-fault transfers were green-lit by the agents**: t2fab05, t33f4ed, t99334c, tf4042f and tfed5bf. The
  deterministic consolidation excludes a repeated fault from delivery whatever the agents say, so these were not a
  release risk.

### 3.7 Delivery decisions (the four-minute rule)

The harness's delivery pass decided every answer under `delivery-v1`, with the 240 s translation budget and the 0.90
threshold.

| Measure | As recorded | Replay at `f2329df` |
| --- | --- | --- |
| Answers decided | 24 | 24 |
| FORMALLY CHECKED / OVERSEER-SELECTED / NOT CHECKED / withheld | 0 / 0 / 0 / 24 | 0 / 0 / 0 / 24 |
| Pass receipts equal to the genuine records | 24 of 24 | 24 of 24 |
| Time to decision | 0.30 s to 18.70 s (results audit) | 0.15 s to 12.5 s |
| Within the 240 s budget | all | all |

- **Why every answer was withheld.** The harness calls no model. So no fidelity reviewer ran, and no formal path could
  complete. No overseer agent was configured on the pass either, so the fallback established no accuracy, and
  withholding is the policy's default.
- **The overseer-selected fallback above 90% was not exercised in round 8.** The round's overseer agents were not
  connected to the delivery pass.
- **At `32a5c0e`** (its commit message): all 24 decisions are still withheld, with the mode, the delivered flag and the
  label unchanged. 22 receipts name rule `formal-label-withheld`; the other 2 answers have no deliverable.
- **What the results audit checked.** Every label passed `is_fallback_label_honest`, and every delivery receipt
  verified.
- **What blocked delivery on the recorded run.** 15 of the 24 candidates were excluded from any delivery, 13 of them by
  false error-level findings on correct answers. Four were marked refuted by signed results that refute correct claims.
  The clearance's fixes removed the false STEM errors.
- **After the fixes.** On the replay at `f2329df`, two answers are still excluded (no deliverable consolidation). Every
  other answer is withheld for an unresolved claim: an ambiguous, unsupported or invalid translation, or an ungrounded
  dependency with no fidelity review.

### 3.8 The replay of round 8 on `f2329df`'s tree

This replay was run on `f2329df`'s tree, when this page was first written, to check the figures above. It used a fresh
copy of the recorded round and `run_arena.py <copy>`, with no model called. It is one run on a shared development
machine, not a stress or latency measurement.

| Measure | Value |
| --- | --- |
| Harness wall time | 246.2 s (the round's own run took 289.4 s) |
| Transport | 203 of 203: genuine traffic 48 of 48 (24 replies, 4 relays, 20 syntheses), injected faults 155 of 155 |
| Genuine records with an error-level finding / with warnings only | 0 / 30 |
| Fixture coverage | 451 of 469 served, all by claim id only (QUALIFIED: TRANSLATIONS_LOST, FIXTURES_UNBOUND) |
| Claim counts and outcomes | as in section 3.5 |
| Hub time per transmission: genuine median / 95th percentile / max | 183 / 1,422 / 1,995 ms |
| Hub time per transmission: injected faults median / 95th percentile / max | 702 / 2,009 / 3,314 ms |
| Delivery pass | 24 decided, 24 withheld, 24 of 24 receipts equal to the genuine records, no error; time to decision 0.15 s to 12.5 s; the pass took 95.2 s |

Apart from result ids and timings, the summary is identical to the clearance's own replay of the same material.

### 3.9 The overseer agents

These figures come from the round's overseer-agent wave, scored with `overseer/scripts/score_verdicts.py`
(`assess_export` and `score`, with `combine_verdicts` per transfer). The verdicts are agent self-reports scored against
signed engine results.

| Measure | Value |
| --- | --- |
| Transfers judged / dossiers | 30 / 60 |
| Pool instances / duplicates spawned | 4 / 0 (each transfer went to 2 instances; 60 units over a quota of 8 asked for 8 instances, capped at 4) |
| Verdicts valid / invalid (production intake and `validate_overseer_verdict`) | 60 / 0 |
| Dossier digests matching the transfers rebuilt from the journal | 60 of 60 |
| Agent-findable faults present / named | 30 / 1 (a confirmed `translation_circular` on ta414dc) |
| Accusations confirmed / unresolved / refuted | 1 / 20 / 1 |
| False accusations accepted | 0 (the one false accusation was refuted by a deterministic check) |
| Contested transfers / resolved | 9 / 0 |
| Repeated-fault transfers stopped | 3 of 8, held for human review; the other 5 were green-lit (see 3.6) |
| Contradictions of signed results / caught | 0 / 0 |
| Green-lit transfers | 17 |
| Overseer time, total / median per instance | 4,524.9 s / 1,163.8 s |

Gates:

- **False-accusation gate: NOT MEASURED.** Its bounds are 0.0 to 0.078 of clean transfers. Eight unresolved
  accusations on clean transfers need human adjudication first.
- **Every verdict produced by the package's runner: FAIL.** All 60 verdicts were self-reported by agent sessions, not
  produced through `OverseerAgentRunner`. So these verdicts could not have fed the delivery policy.
- **Injection gate: NOT MEASURED.** The agents did not follow the instruction planted in the Spanish text, and they
  flagged it as dossier text.

The gold labels behind "1 of 30" were themselves at fault. Re-adjudication after the clearance (`docs/OVERSEER_RESULTS.md`
section 35) found the following among the 30 agent-scorable faults:

- 22 sit on translations the fidelity lens judged faithful, so they are now false findings an agent is credited for
  disputing;
- 7 are no longer raised by the corrected auditor;
- 1 remains.

The 11 injected faults that the recorded receipts did not name are now agent-scorable gold. The wave's verdicts were
not re-scored against the corrected gold.

The agents also found faults that the scorer credits to no one: five STEM faults the hub missed, two false hub findings,
and the dropped Questions 2 and 3 of a Mathematics AA answer.

## 4. What the round-8 clearance fixed (commits `f2329df`, `32a5c0e` and `5060a52`)

Each fix has a regression test with a clean control. `f2329df` holds the fixes listed under STEM, Overseer and
Harness, and the first form of the note rule. `32a5c0e` narrows that rule and adds rules 6c and 6d (under Delivery
policy). `5060a52` fixes the three regressions listed last.

- **STEM** (`docs/STEM_DESIGN.md` section 39, `docs/STEM_RESULTS.md` 10.15).
  - The 14 false INT-SUBJ-001 on correct work are gone. Causes fixed include a symbolic step's own definitions, a
    cancelled factor that may not be zero, a value restated in another unit, a unit after a surd, rejected values and
    evaluation points read as roots, Markdown list markers read as minus signs, count nouns and truncated GDC decimals.
  - Previously silent faults are now named: a miscopied or swapped request value, prose shares, a wrong booklet
    constant, a wrong mole ratio, and Boolean outputs and truth tables.
  - A relation reached by a bidirectional control character is decided in neither order, and the channel refuses a
    specialist response that holds one (INT-REQ-009).
- **Overseer** (`docs/OVERSEER_DESIGN.md` section 50, `docs/OVERSEER_RESULTS.md` section 35).
  - On the 20 genuine channels, errors fell from 3 to 1. The one left is OVS-RCPT-004 on p8a, which was present before
    too.
  - A conflict that exists only through pooling a rejected candidate is now named (OVS-JOINT-003).
  - Pack 1.5 is installed.
- **Delivery policy** (`docs/DELIVERY.md`).
  - CORE-QNT-001 and CORE-CHR-001 now block FORMALLY CHECKED.
  - A "Next step:" or "Note:" paragraph is a note, not a self-report (rule `meta-note`), only when a closed allowlist
    reads it as a study suggestion, an inability to see or open a named source, or content not checked. The clearance
    commit `f2329df` read a bare note as a note whenever it held a limitation word such as "not" or "only", and the
    independent push check held it on this rule: it let an assurance written as a note ("Note: there is nothing to fix
    in this answer, not a single slip.") travel under the label. The follow-up commit `32a5c0e` narrows the rule to that closed
    allowlist, read from the block's first character. It refuses the label for any block that opens with a note or
    sources lead and is read neither as a note nor as a pure source list (rules `lead-blocks` and
    `source-list`), and for any text the branch's parser reads as no claim unless a closed reader reads it whole as a
    note, a source list or a bare layout label (rules `non-material-text` and `layout`). Every claim must carry a
    positive signed engine outcome (rule `unverified-claims`, 6c), and the label is withheld for every answer in this
    release (rule `formal-label-withheld`, 6d). Every one of these rules can only remove the label. A refusal-only rule
    that raises refuses the label, with a reason that names the rule and the exception type. The fallback still decides
    the mode; before `32a5c0e`, the whole decision was withheld.
- **Harness** (`docs/ARENA_RESULTS.md`, "Round 8 clearance").
  - The replay now passes the task record to the translator as production does.
  - Fixtures can be bound to their claim text.
  - Retries that a recording cannot exercise are named.
  - Syntheses are stamped when they are relayed.
- **The three regressions fixed in `5060a52`.** The publisher's simulation of `32a5c0e` found them. Each one was hidden
  because no verification of `f2329df` or `32a5c0e` supplied the recorded rounds or ran the overseer's contained run.
  The fix is ported onto the sub-project layout of `ab44c8a`.
  - The re-keyed round-7 overseer test still expected OVS-TRN-006 on mai-t13 m1.1 and m7.1. The translator's semantic
    circularity gate now withholds both encodings at translation (E112), so the test asserts that withholding first.
  - Rule `declined-bound` accepted a declined answer's stated word count without a recount. The auditor now recounts
    first, and raises OVS-FORM-003 naming MEASURED when the stated count differs (design Decision 111).
  - Rule `derived-figures` traced a planted figure through values that the request or a supplied text only implies. So
    two STEM probes (units-translation and units-translation-prefix) were no longer named. Figures are now taken only
    as written.
  - With the recorded rounds supplied, the contained run of `5060a52` passes all 14 of its gates: 355 of 355
    tamperings are detected, the 16 controls are clean, the 677 STEM probes leave no probe class failing, and rounds r2 to r5
    stay at 46/46 and r7 at 177/177. The publisher's run of `32a5c0e` had detected 353 of 355 tamperings, with two
    probe classes failing.

**Tests rewritten to a stricter rule (none weakened or deleted).**
- One STEM test: a cut decimal inside an expression is now decided, and must fail when wrong.
- Two overseer tests that pinned the old reading of cut decimals: the formal-check count of r7's mai-t13 went from 13
  to 15, and the D32 sentence changed.
- At `32a5c0e`: five end-to-end tests (287 cases) passed whatever the 6b rules did. They now require the named rule's
  own reason. 17 test functions were renamed to say what they check, with their cases unchanged.
- At `5060a52`: the re-keyed round-7 overseer test asserts the withholding first and keeps its old pins on the encodings
  delivered past the gate. A new test checks its pins against the shipped record without the recorded rounds.

Each rewritten test says so in its docstring, and `tests/README.md` lists them.

**Left open by the clearance** (from the fixers' notes in `f2329df`'s message and the design sections):
- The channel-wide naming of bidirectional controls for every subject. The clearance's handoff fixer closed this in the
  same commit: the channel refuses such a response for every subject (INT-REQ-009, rule bidi-text; `tests/README.md`).
- Share forms and quotation warnings on the non-STEM branches. The handoff fixer added prose shares to those branches in
  the same commit (`tests/README.md`).
- One false INT-SUBJ-004 warning on correct work (ph-t14 s7.2).
- "So mgh = ½mv² and v² = gh" read as one statement.
- The non-STEM findings of other owners: Economics scale words, quotation crediting and marks.

Left open by `32a5c0e` for round 9 (the label stays off until then):
- a label policy that holds under attack, after which the label returns;
- assurances the parser reads as claims (quoted or fullwidth notes, plain-prose assurances), which rules 6c and 6d
  refuse for now;
- Unicode tag characters inside claims;
- the English segmenter, which is quadratic on unpaired closing quotes;
- the integration kit's per-claim text "Formally checked: in its logic encoding ...", which must never be shown as an
  answer-level label.

Left open by `5060a52` (minor):
- the reciprocal reading still does not require a written division;
- tampering T5's fallback takes any not-applicable record, not only declined-bound ones;
- rule task-and-supplied no longer traces figures written in words;
- three tamperings lost a secondary code (T4 OVS-RCPT-008, T22a OVS-JOINT-002, T23v OVS-TRN-005).

Carried from the integration gate:
- The synthesis ledger's work bounds are spent in claim order, so a padded synthesis can carry a changed date past the
  bound with only a warning. Such a synthesis is released labelled "not verified", never as verified.
- A claim verifier that raises makes the transfer audit fail falsely, so the answer is withheld (`docs/DELIVERY.md`).

## 5. The optimisation check

**The optimisation check has not run, and it changed nothing.** The optimisation record for round 8 is empty, so there
are no before-and-after timings to report.

The founder's order puts bug testing and fixes first and optimisation last. A performance finding that changes no
receipt, finding or status is recorded with its measurements for the optimisation checks, not fixed. The clearance
deferred no new one. The findings recorded so far:

| Finding (no outcome change) | Measured | Where recorded |
| --- | --- | --- |
| The arena delivery pass replays every genuine answer a second time | 3.4 s to 6.2 s on r1 to r6; 13.0 s on r7 (r7 harness 35.9 s to 44.4 s) | `docs/DELIVERY.md` |
| Large answers take more than 5 s, growing with the number of formal checks | round 6 | `docs/ARENA_RESULTS.md` |
| One replay worker runs jobs in turn; the stage timings omit most of a replayed problem's solver time | 20 replays 43.5 s; 2.1 s per problem, about 33 ms reported | `docs/OVERSEER_RESULTS.md` |
| The number reader's per-figure slices | 3.6 s on 400,000 characters of figures | `docs/OVERSEER_RESULTS.md` section 33 |
| The shadow decides every check a receipt states not run | 68 of 128 checks; audit 1.99 s against 1.83 s | `docs/OVERSEER_RESULTS.md` section 34 |

One timing did change during bug testing. The clearance fixed an overseer input stall as a bug, not as an
optimisation: an IR of 200 untraced figures checked against an answer stating 20,000 figures fell from 17 s per
translation to 1.0 s, then 0.3 s per further claim (`docs/OVERSEER_RESULTS.md` section 35).

## 6. The external review of 12 October 2026: findings and disposition

The external review raised nine findings and two evaluation items. All were fixed in commit `22d6a5b` (17 October 2026;
`REVIEW_FIXES_README.md`), each at its cause and with regression tests. Negative controls show that the rejected
conclusion really is wrong. An independent verification accepted all twelve items (the nine findings, the two
evaluation items, and the rule that no test is weakened) after five rounds. Findings 2 and 6 were repaired a second
time, inside the same commit, after the second verification. The upgrade path was tested on genuine signed results of
earlier releases.

| # | Finding | Disposition |
| --- | --- | --- |
| 1 | Exact claims repaired into approximate ones, so a widened figure could earn a solver success | Fixed in `22d6a5b`. Exactness is read from the source wording; a widened retry blocks release |
| 2 | Model-chosen trusted grounding kinds hid unsupported premises | Fixed in `22d6a5b`. Authority comes only from a check run in this process, and only for a premise's whole content; every unverified dependency is listed and blocks release |
| 3 | Turning off the unsat core removed dependency evidence and bypassed E108 | Fixed in `22d6a5b`. The core is always extracted |
| 4 | The fidelity reviewer did not see the original evidence | Fixed in `22d6a5b`. The review is bound to the task, the supporting claims and the supplied texts |
| 5 | A signed result from an earlier release passed current binding checks | Fixed in `22d6a5b`. Build, schema and policy identities are bound; an earlier result is never current |
| 6 | E110/E111 withheld valid counterexamples | Fixed in `22d6a5b`. A figure is withheld only when a source positively asserts it |
| 7 | A partially checked reference list was marked verified | Fixed in `22d6a5b`. Every reference is validated on its own |
| 8 | Effective validation limits were absent from the result binding | Fixed in `22d6a5b`. `limits_digest` is bound |
| 9 | Numeric grounding depended on notation | Fixed in `22d6a5b`. Figures are typed exact quantities |
| E1 | One headline functional rate | Fixed in `22d6a5b`. Transport, coverage, fidelity and claim counts are reported separately |
| E2 | A timing-sensitive parser test | Fixed in `22d6a5b`. Stabilised without relaxing its bound (`tests/timing.py`) |

**Still open from the review: none.**

One related gap remains, and it belongs to the integration owner. The integration kit's fixture path
(`integration.verifier.FixtureCorpus`) calls its verifier without the task record. Since the round-8 harness fix, the
arena's result digests differ from that path's on the two simulation items whose fixtures carry task-authority premises
(`docs/ARENA_RESULTS.md`, "Round 8 clearance").

## 7. What is not yet shown

- **The 98% target.**
  - No lens has reached 0.98 in any round from 1 to 8. Round 8's five lenses gave 0.1921, 0.3962, 0.7561, 0.1474 and
    0.9424.
  - The transport count of 203 of 203 is a different measure. It does not say the findings are true.
  - Round 9's five lenses (integrated round c2, run on `c4f276c`) judged the tree after the clearance and the
    architecture step. None reached 0.98: adversarial live 0.7729, translation fidelity 0.8356, communication fidelity
    0.6503, results audit 0.3138, STEM integration 0.1939. Each lens answers its own question, as in section 3.1.
- **Round 9's fix stage.** This page does not report its measures; `tests/README.md` records them. **Round 10** has
  not run.
- **Live-model accuracy.** No live translation provider or overseer model was called by any test, replay or harness run.
  - The round's specialists and overseer agents were agent sessions. Their verdicts were self-reported, not produced by
    the package's runner, so the runner gate fails.
  - Translation fidelity on the current code is not measured.
  - The overseer agents' gates for contradictions, false accusations and injection-following are not measured for any
    deployed model.
  - The overseer-selected fallback above 90% has never delivered an answer in an arena round. Since round 9's fixes, the
    harness can run its delivery pass with overseer agents (`run_arena.py --overseer-provider`). The agents then go
    through the package's runner, and the decisions are reported beside the withheld baseline. No round has been
    replayed that way yet.
  - The cheapest tier's fit to the knowledge pack is untested.
- **Stress and load.** No stress iteration has run since the round-2 fix round, by instruction. The only load test
  planned is the multi-agent scalability test of the Scaling phase.
- **Deployment.** Nothing is deployed. The integration kit is not connected to the delivery policy. The kit's fixture
  path does not pass the task record (section 6).
