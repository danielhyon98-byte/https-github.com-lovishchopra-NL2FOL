# Delivery policy: the four-minute formal path, the overseer-selected fallback, and what is withheld

This document describes `epinoic_logic.overseer.delivery_policy` (policy version `delivery-v1`). The policy decides what
the router may hand on for one deliverable, and it records why in a signed receipt.

## The requirement

The founder set three rules:

1. The Z3 logic code must translate an answer completely within **four minutes**.
2. If it does not, the **overseer agents** check the candidate outputs, and the candidate with the highest accuracy is
   delivered.
3. That candidate is delivered **only when its accuracy is above 90%**.

The policy applies these rules to one deliverable at a time. A deliverable is a specialist's answer, or the consolidated
response when several agents answered the same input. The policy gives one of four outcomes:

| Mode | When | Label starts with |
| --- | --- | --- |
| `formally_checked` | Within the translation budget, every material eligible claim reached a definitive, clean outcome. | `FORMALLY CHECKED within the 240 s translation budget` |
| `overseer_selected` | The formal path did not complete. The best candidate's validated accuracy is above the threshold. | `OVERSEER-SELECTED (not formally checked, not verified)` |
| `not_checked` | The overseer stage established no accuracy, and the operator configured this outcome. | `NOT CHECKED (not formally checked, not verified, no accuracy established)` |
| `withheld` | Every other case. | `WITHHELD (not formally checked, not verified)` |

Results prove properties of the encoding only. Every receipt carries the engine's scope statement followed by the
policy's own sentence. An overseer-selected answer is chosen by an advisory review. It is never a verification, and its
label says so.

## Using it

```python
from epinoic_logic.overseer import DeliveryPolicy, load_pack

policy = DeliveryPolicy(pack=load_pack(exported_pack_zip),        # the EXPORTED knowledge pack
                        provider_factory=lambda agent_id: provider)  # one completion provider per overseer instance
session = policy.start(hub, task_id)   # when the deliverable's first answer reaches the hub (the hub needs its auditor)
session.install()                      # the deadline-bound verifier goes on the task's channel
...                                    # hub.receive(...) for every answer to the input
decision = session.decide(request_message_ids=[...], receipts={message_id: receipt, ...})
if decision.delivered:
    hand_on(decision.answer)           # DeliveredAnswer: the journaled payload, its mode and label, the receipt id
store(decision.receipt)                # DeliveryReceipt, signed under key id overseer-delivery
```

`policy.start` refuses a hub without the transfer auditor (`AuditorNotAttached`). Nothing is delivered without the
transfer audit. `decision.delivered` is the only field that permits handing anything on. A session decides once.
After the decision, the channel's previous verifier is restored. One policy may decide several deliverables at once.
Only the overseer stages are serialised, because their instances share the stage's deadline. A deliverable's formal path
never waits for another deliverable's overseer stage.

`DeliveryPolicy(clock=...)` takes a monotonic clock, `time.monotonic` by default. The tests inject a fake clock. Without
a pack and a provider factory, the fallback has no overseer agent, so it never establishes an accuracy. The arena
command line runs this way because the harness calls no model.

## The formal path

The formal stage opens at `policy.start`. Its deadline is `start + translation_budget_s`, which is 240 s by default.
`session.install()` wraps the channel's claim verifier in a `DeadlineVerifier`:

- A claim whose verification would start at or after the deadline is not started. It gets no outcome (`NOT_ATTEMPTED`)
  and is recorded as `skipped_budget`. It is never shown as a success.
- A claim whose verification finishes after the deadline is `late`. Its outcome stays on the channel's receipt, but the
  formal path is out of budget.
- The inner verifier is called as the channel would call it: with the task record only when it declares a `task`
  parameter.

A verification already in progress is not pre-empted. The engine's solver limits and the provider's own timeout bound
it. The deadline stops new work from starting.

`decide` completes the formal path, delivering FORMALLY CHECKED, only when all of the following hold:

1. **Within budget.** The formal stage ended at or before the deadline, and no claim was skipped or late. Time spent
   waiting before the decision counts.
2. **There is a deliverable.** The consolidation of the answers to the input has a deliverable status, and
   `consolidate.delivery_decision` allows the delivery. Conflicting answers, or answers that are all excluded, are not
   deliverable.
3. **Every material eligible claim is clean.** The material claims are those whose materiality is `material` and whose
   role is not `other`. Eligibility is decided deterministically by the eligibility rules and the subject policy. A
   clean claim meets all of these conditions:
   - It is `TRANSLATED` with no ambiguity flag.
   - Its display status, re-derived under the auditor's verification key, is definitive.
   - The release rule `release-v1`, re-derived from the journaled translation and signed result, permits it. That rule
     covers the engine's release check, every relied-on premise being established (so no premise authority is
     unresolved), no failed grounding check or partial reference, no retry that changed the claim, and a current
     `faithful` fidelity review made with the evidence.

   The stored `display_status` and `release` fields are never trusted.
4. **At least one claim is eligible.** An answer with no eligible material claim is never formally checked: vacuous
   success is no success.
5. **No error-level finding on the receipt.**
6. **Every branch formal check holds.** These are the report's own STEM, arithmetic and chronology checks.
7. **No objection from the transfer audit.** The overseer's translation checks (`OVS-TRN-*`) name none of the material
   claims. The latest verified task audit names the answer in no error. The transfer's clearance lets the router act
   (`policy.act_decision`).

Any other result is the fallback. The formal path's `reasons` say which condition failed: a budget overrun, a skipped
or late claim, or an unresolved claim. An unresolved claim can be ambiguous, invalid, unsupported or untranslatable,
undecided (`TIMEOUT`, `UNKNOWN`), unreviewed or unfaithful, a failed grounding check, an unvalidated premise, or refuted.
An unresolved formal path falls back at once and does not wait for the budget.

## The fallback

### Candidates

The candidates are every answer to the input that the channel delivered:

- duplicated instances of one specialist;
- several specialists answering the same input;
- a single answer, which is one candidate.

The consolidation orders them. Its canonical answer comes first, then each group's representative in the
consolidation's group order, then the other members of the groups, then the answers in no group (the excluded ones), in
journal order within each tier. Answers the channel rejected are listed as non-candidates.

A candidate may be delivered only if it passes the **integrity gates**:

- The consolidation does not exclude it. An excluded answer has an error-level finding on its receipt or in the task
  audit, a clearance that did not pass, or a repeated fault (`OVS-REP-001`). The consolidation's own rule says an
  excluded answer is never delivered.
- The router may act on its clearance at the moment of selection.
- Its journaled payload carries its envelope's digest.

A failed translation is a warning on the receipt, never an exclusion. This covers invalid, unsupported, ambiguous,
undecided and not-attempted translations. Translation failures are what the fallback is for.

### The overseer stage

The overseer agents review the task through `hub.review_pool([task], pool)`:

- The pool is the policy's own `OverseerPool`, built from the exported pack.
- Each instance runs the package's `OverseerAgentRunner` on the cheapest model tier.
- The pool is sized deterministically: one instance by default, and two independent instances for a task with a
  repeated fault. It never goes past the maximum, which is four by default.

Every reply goes through the production intake and `validate_overseer_verdict`, with no shortcut.

Each verdict then gets a **standing**. A verdict that contradicts a signed engine result is **rejected** (OVS-AGENT-001),
and none of its reviews counts. A contradiction is an engine statement the stored result refutes, or an accusation (or
part of one) refuted by a signed result. An accusation refuted only by a deterministic check is set aside: it lowers no
score, and the verdict still counts. Semantic accusations (`translation_unfaithful`, `other`) are decided by no check, so
they are unresolved. They can lower a score. They never confirm anything.

### Accuracy

The accuracy of a candidate is the share of its material claims that the validated verdicts confirm accurate. The
receipt records each material claim with one assessment and its evidence:

| Assessment | When |
| --- | --- |
| `inaccurate` | A signed engine result refutes the claim. Either its display status is COUNTEREXAMPLE, INCONSISTENT_PREMISES or UNSATISFIABLE, re-derived and authentic, or an error-level check names it and cites a signed, definitive result. A claim is also inaccurate when a deterministic check faults it: an error-level receipt or task-audit finding, or an agent's accusation that a check confirmed. |
| `contested` | A counted verdict accuses the claim and the accusation stays unresolved or unverifiable. |
| `unassessed` | No counted verdict examined the claim's transfer. |
| `accurate` | At least one counted verdict examined the transfer (`transfers_reviewed`). No fault is pinned on the claim, no check names it in an error, and no signed result refutes it. |

An unassessed claim is never accurate.

### Selection

Selection is deterministic and runs in five steps:

1. **Integrity gates.** A candidate that fails them is never delivered.
2. **Refutation rule.** A candidate with a material claim refuted by a signed engine result is never delivered while
   another candidate has none.
3. **Fault rule.** This rule is stricter than the founder's. A candidate that a deterministic check faults is never
   delivered while another candidate has no such fault. A fault includes an error-level finding on a supporting claim,
   such as an invented quotation in the evidence.
4. **Ranking.** Candidates are ranked by accuracy, compared as exact fractions. Ties go to the consolidation's canonical
   order.
5. **Threshold.** The best candidate is delivered only if its accuracy is **above** `min_selected_accuracy`, strictly.
   The default is 0.90. The comparison is exact (`accuracy_above`): 9 of 10 is 0.90 and is withheld, while 10 of 11 is
   delivered. An operator may raise the threshold. A threshold below 0.90 is refused.

No acceptable candidate means withheld, with every candidate's score and reasons on the receipt. A single candidate
keeps the founder's threshold. If one of its claims is refuted, that claim counts as inaccurate, which lowers its
accuracy, and the receipt names the refutation.

### The overseer stage's deadline

The overseer stage has its own deadline, `overseer_budget_s`, which is 240 s by default. Each instance's provider is
wrapped, so:

- a call that would start at or after the deadline is not made;
- a reply that arrives after the deadline is not counted.

Either way the runner records a provider failure, never a verdict. If the stage runs out of budget, fails, or has no
overseer agent configured, no accuracy is established. The answer is then:

- **withheld** by default; or
- delivered **NOT CHECKED**, only when the operator sets `on_overseer_timeout="deliver_canonical_not_checked"`. The
  answer is the consolidation's canonical one. It must still pass the integrity gates and the refutation and fault rules
  against the other candidates. Without a deliverable consolidation (for example, conflicting answers) it is withheld.

The NOT CHECKED label states that no accuracy was established.

## Honest labels

- **The mode and label travel in two places.** They are in the signed receipt and in the delivered payload
  (`DeliveredAnswer`, contract `delivered_answer/1.0`).
- **The labels are fixed templates with figures only.** No reason text or agent text reaches a label.
- **Only `formally_checked` claims a check.** Every other label says "not formally checked" and "not verified", and it
  never states either phrase without the negation. `is_fallback_label_honest` checks this, and every test applies it.
- **The fallback's reasons are on the receipt.** These are why the formal path did not complete (`fallback.why`) and the
  selection evidence (`fallback.selection` and every candidate's assessment).
- **A delivered answer the formal path did not decide carries its evidence too.** It holds the formal path's reasons
  (`formal_reasons`), the selection notes (`selection`) and, for `overseer_selected`, the chosen candidate's accuracy
  (`accuracy_fraction`), all copied from the signed receipt. `verify_delivered_answer` fails if any of them differs.

## The fallback never edits

The delivered payload is the chosen answer's journaled payload, copied byte for byte. Its digest is the envelope's
digest, and the receipt records it (`verify_delivered_answer`). No claim is edited, no number widened, no premise added
and no difficult claim dropped. Every material claim is scored, so none is dropped from the record either. Nothing is
translated again, no transfer is added to the journal, and no receipt changes. The router's copy is a deep copy.

## The receipt

`DeliveryReceipt` (contract `delivery_receipt/1.0`) is frozen and signed under the overseer's `delivery` subkey (key id
`overseer-delivery`, derived from the one overseer secret like the other subkeys). It records:

- The mode, whether an answer was delivered, and the label.
- The delivered message, receipt, agent, report and payload digest.
- The budgets and the threshold.
- **`time_to_decision_s`**: from `start` to the decision.
- **`translation_s`**: the formal stage.
- **`overseer_s`**: the overseer stage, or none when it did not run.
- The formal path: every material claim's outcome, the branch checks, the skipped and late claims, and the reasons.
- The fallback: why it ran, the overseer stage (instances, plan reasons, runs, provider calls with their timing, verdict
  standings, audit ids), every candidate's assessment, the non-candidates, the chosen message and the selection notes.
- The consolidation and task audit ids, the reasons and the scope statement.

`verify_delivery_receipt` fails on any edit, on another key, or on another secret.

## Configuration (`DeliveryConfig`, strict and frozen)

| Field | Default | Bounds |
| --- | --- | --- |
| `translation_budget_s` | 240 | above 0, at most 3600 |
| `overseer_budget_s` | 240 | above 0, at most 3600 |
| `min_selected_accuracy` | 0.90 | at least 0.90, below 1 |
| `on_overseer_timeout` | `withhold` | `withhold` or `deliver_canonical_not_checked` |
| `clearance_wait_ms` | 250 | 0 to 250 (the router policy's bound) |

## The arena report

`scripts/arena/run_arena.py` adds a delivery pass to every round. The pass runs after the round's records are complete,
on a hub of its own with a transfer auditor:

- It replays each group's genuine traffic in the genuine pass's order: requests, peer relays and answers, with the same
  fixtures.
- It opens a delivery session for each answer and decides.

It adds no record and moves no transport count. Its hub and its claim verifier are bound when the module is imported,
so a harness that replaces the module's `RouterHub` or `verify_claim` never reaches the pass. The contained harness
(`scripts/overseer/ovs_harness.py`, and the contained run's plain copy) switches the pass off (`DELIVERY_PASS = False`)
while it runs, because its runs measure the transfer auditor; `deliveries` then says the pass was not run.

`results.json` gains `deliveries`, which holds:

- the policy, budgets and threshold;
- the count per mode;
- for every task: the mode, the label, the time to decision, the translation time, the overseer time, the formal path's
  reasons and claims, every candidate with its accuracy and whether it was chosen, the chosen answer, the receipt id and
  whether it verifies, and whether the pass's receipt equals the genuine record's (status and codes);
- the pass's errors and wall time.

`summary.md` gains a "Delivery decisions" table with one row per task: mode, time to decision, translation time, overseer
time, candidates with their accuracy, the chosen candidate, and the first reason.

The command line configures no overseer agent because the harness calls no model. A replay also calls no fidelity
reviewer, so no formal path completes and every answer is withheld with its reasons. That is the honest outcome without
models. `run_round(round_dir, delivery_overseer={"pack": ..., "provider_factory": ...})` configures overseer agents
(see `tests/e2e/test_arena_deliveries.py`).

Measured on fresh copies of the eight recorded rounds (rounds 1 to 7 and the adversarial variant of round 1):

- **Transport counts are unchanged.** Round 1 is 30 of 30, its adversarial variant 150 of 151, rounds 2 to 6 are 46 of
  46 each, and round 7 is 177 of 177.
- **Every record is unchanged** apart from latencies and result ids.
- **Every answer gets a decision.** The pass decided 79 answers (4, 23, 6 per round for rounds 2 to 6, and 22) with no
  error. All 79 were withheld, as above. By first cause:
  - 44 had an eligible claim with no recorded translation served, so it was not attempted;
  - 20 had every eligible claim translated, but no fidelity review, so release was refused;
  - 13 had no deliverable consolidation, because the answer carries an error-level finding;
  - 2 had no material eligible claim.
- **Every receipt matches.** All 79 delivery-pass receipts equal the genuine records' (status and codes).
- **Decisions are fast.** The longest time to decision was 1.9 s.

## Two overseer faults found by the formal path (fixed)

Before these fixes, no reviewed answer could ever be delivered FORMALLY CHECKED through an audited hub.

1. **`checks/translation.py` `summary_matches`.** The function listed its review-currency alternatives with
   `dict.fromkeys((report, None))`. A `SpecialistReport` is a frozen model whose claims are a list, so hashing it raised
   `TypeError`. The translation check of every outcome carrying a fidelity review therefore failed internally
   (OVS-AUDIT-001, error), and every reviewed transfer's clearance was AUDIT_FAILED. The alternatives are now listed
   without hashing.
2. **`checks/translation.py` `grounding_faults`.** The function re-ran the grounding check without the task record. A
   premise that the task record validated (`numeric_in_task`, `relation_in_source`) could not be reproduced, so every
   genuine task-validated premise was named overstated (OVS-TRN-003, error). The re-run now gets the task record of the
   journaled request, used only when its digest is the one the translation records (rule `task-record-rerun`). A
   verification the task does not support is still named.

Regression tests with clean controls are in `tests/overseer/test_delivery_overseer_fixes.py`.

## Findings recorded, not fixed here

- **A verifier that raises never yields a deliverable answer.** The channel records the exception as a warning
  (INT-REQ-006). The shadow channel, fed the journaled inputs, cannot reproduce the exception and issues ACCEPTED, so
  the transfer audit fails (OVS-RCPT-008, AUDIT_FAILED) and the consolidation excludes the answer. The outcome is
  conservative: the answer is withheld and never shown as a success. The audit failure is still false.
  `tests/overseer/test_delivery_policy.py::test_a_verifier_that_raises_records_the_failure_and_never_delivers_formally`
  reproduces it. It belongs to the bug-testing phase.
- **Performance.** The arena delivery pass replays every genuine answer a second time, with eager inline replay, which
  repeats work the round already did. This changes no receipt, finding or status, so it is recorded for the
  optimisation checks only. Each round's `deliveries.wall_s` measures it. The pass took 3.4 s to 6.2 s on rounds 1 to 6
  and 13.0 s on round 7. Round 7's harness wall time went from 35.9 s to 44.4 s.

## Limits

- **It is not a verification.** An overseer-selected answer rests on an advisory review. Its accuracy says how many
  material claims counted verdicts examined without finding a fault. It does not say that the claims are true.
- **No live provider integration is claimed.** The tests use scripted providers and fixture translators.
- **The integration kit is not connected to the policy.** The kit's decision table and its checks port
  (`src/epinoic_logic/integration/`) do not consult the policy yet.
- **The policy decides per answer or consolidated response.** The combinator's synthesis is gated by
  `policy.may_release` as before, not by this policy.
- **A verification in progress at the deadline is not interrupted.** It finishes and is marked late. The deadline only
  stops new claims from starting.

## Tests

| File | What it covers |
| --- | --- |
| `tests/overseer/test_delivery_policy.py` | The formal path: a fast clean answer, and several claims. The budget: no fallback inside 240 s; the fallback after it, with late and skipped claims; the 240 s boundary; a configured budget; time spent before the decision. Every unresolved outcome, with and without overseer agents. Nothing eligible. A raising verifier. The labels. Receipt and payload tampering. The three times. The configuration floor. Session mechanics. Two deliverables decided concurrently, one never waiting for the other's overseer stage. The policy's own failure. |
| `tests/overseer/test_delivery_fallback.py` | The more accurate candidate preferred over the canonical one. Ties. Exactly 0.90, below and above, compared exactly. A raised threshold. Unassessed claims. An accusation a check refutes. A signed-engine refutation excluding the more accurate candidate. A verdict contradicting a signed result rejected. The overseer deadline, withheld or NOT CHECKED, and no instance called after it. A longer overseer budget. A single candidate. Duplicated instances. A repeated fault with two pool instances. An honest instance against a lying one. That no fallback changes what a claim says. |
| `tests/overseer/test_delivery_overseer_fixes.py` | The two overseer fixes, with controls. |
| `tests/e2e/test_arena_deliveries.py` | The arena report: `results.json` and `summary.md` per task, with and without overseer agents. That the pass moves no transport count. That a replaced `verify_claim` never reaches the pass. That a switched-off pass says so. That the contained harness switches the pass off and restores it. |

None of these is a stress or load test.
