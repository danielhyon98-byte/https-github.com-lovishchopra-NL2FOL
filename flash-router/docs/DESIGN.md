# Flash router design (`epinoic-flash-router` 0.4.0)

## 1. What it is and what it is not

The flash router is the oversight planner's decision maker: it decides how the overseer reviews. It is a separate,
independent agent (this sub-project, package `epinoic_flash_router`), edited, re-tuned and released apart from the
translator, the Z3 engine, the STEM support and the overseer.

It is **not the translator's `RouterHub`**. The `RouterHub` (the translator's `branches/hub.py`) carries every message
between agents through the translator channel and its checks; the flash router never sees a message, an answer, a claim
text or a finding. It is not the website's subject routing either (which picks a specialist). It plans reviews, and its
plans are advice: it never carries, checks, delivers, clears or decides anything.

## 2. Two callers, one port

Both callers reach it only through the router port `epinoic.integration.router-port.v1` (the translator's
`integration/PROTOCOL.md`), JSON text in and JSON text out, in a process of its own:

| Caller | Operations | Documents | The caller's floor |
|---|---|---|---|
| the translator's checks service (section 7a) | `hello`, `plan` | `router-hello.v1`, `routing-request.v1` → `routing-plan.v1` | `minimum-oversight-floor/1` (the service's router port) |
| the overseer pool (section 7b, pool port 1.2; 1.1 still answered) | `pool_hello`, `pool_plan` | `pool-router-hello.v1`, `pool-routing-request.v1` → `pool-routing-plan.v1` | `minimum-oversight-floor/pool-2` (the overseer's `floor.py`) |

The overseer pool attaches the router **by capability**: only a router whose module exposes `pool_hello()` and
`pool_plan()` and whose pool hello declares the capability `pool-plan` at a pool port version the overseer speaks (1.1
or 1.2; this release speaks 1.2, and answers a 1.1 request at 1.1) is attached; any other is refused with `KIT-RT-015` (a failing one `KIT-RT-016`) and the overseer's floor plan runs. The
service attaches it by `EPINOIC_FLASH_ROUTER`. Neither the translator nor the overseer imports this package.

## 3. The minimum-oversight floor, and why accuracy never depends on this router

Agent self-reports and routing advice are advisory. Each caller computes its own deterministic floor from the same risk
signals the router reads, validates the router's plan as untrusted data, and runs it only when it is in contract and at
or above the floor; otherwise the floor plan runs and the refusal is recorded (`KIT-RT-020` below the floor, the
contract's own `KIT-RT` codes otherwise). With no router attached the floor plan runs. Risk signals only escalate. So a
re-tuned or weakened data file, or an edited planner, can add oversight but never remove it.

The pool's floor (`minimum-oversight-floor/pool-2`, in the overseer): every dossier of a batch is reviewed by at least
one instance; a dossier whose task carries a repeated fault or a risk signal (an error-level finding, a rejection, a
contradiction, an encoding conflict, a withheld verdict, a named defect at warning or error, an unchecked source or a
STEM method error at that severity, an argument diagnosis that did not finish), or that the overseer's escalation
advisor escalated, is reviewed by at least two distinct instances; no plan grows past the pool's maximum; every instance
runs on the cheapest tier from the pool's one pack; and since architecture step 3 a combined answer is reviewed N_FOLD,
each source by at least one instance (two when its own transfers carry a risk signal), the merged review by at least one
(two under the same rule), with the temporary context bounded at 65,536 bytes. What lies above the floor is this
router's choice: the batch sizes (how many instances
a batch is spread over), the weight of risk records, extra duplicates, the profile.

## 4. The method table

| Method | Approach | Meaning | Complete reviews | Port plan (rules/4) | Pool plan (rules/4, pool port 1.2) |
|---|---|---|---|---|---|
| `IN_DEPTH` | in-depth examination | one instance examines the whole response | 1 | one review, one part, when it fits one instance's budget | a dossier that is not escalated |
| `SPLIT` | duplication | the work divided across parallel instances, each part reviewed once | 1 | an output read by one review that does not fit one instance, in the fewest parts that fit | not for one dossier (a dossier that does not fit is disclosed, `over_budget`); a batch over the quota is spread over instances |
| `DUPLICATE` | duplication | independent duplicate reviews, combined by the verdict combination | `reviews` | two or more reviews, in parts when the output does not fit | an escalated dossier, `escalated_reviewers` instances; a combined answer's escalated source |
| `N_FOLD` | duplication | a combined answer's sources each reviewed on instances of their own in parallel, then one merged review with the temporary context of their validated outcomes | `reviews` | a combined answer's synthesis, its merged review read whole and fit-checked (`over_budget` when it does not fit) | a combined answer (P8) |

The table is data (`methods` in the rules file).

## 4a. The flash decision maker (rules D1 to D7, `decision.py`)

The router's first decision, for every response it is asked about (an output of the service's routing request, one
dossier of a pool batch), is made by code:

- **D1 what it reads**: the request record's and the output's features only (risk signals and records, sizes, STEM or not,
  translated claims, the topology), never a text; deterministic and instant; no model decides duplication, and the
  overseer's escalation advisor only adds escalations (an item's `advised`).
- **D2 the two methods**: the in-depth examination method (`IN_DEPTH`) and the duplication method (`SPLIT`, `N_FOLD`, with
  `DUPLICATE` where risk calls for agreement).
- **D3 agreement**: the reviews a response needs come from its risk signals (port rules 2 and 3, pool rule P2, P8 for a
  combined answer's parts); risk only raises them.
- **D4 fit**: an instance keeps accuracy only when it reads what it examines whole: the system text of the knowledge
  pack's composition the content needs (the cost data's `system_text_chars`, the sizes of the pack the overseer sends,
  which the cost data names as `recorded.system_text_pack`), what it reads and the output budget within
  `instance_budget_tokens`. A response that does not fit is divided into the fewest parts that fit (at most `max_parts`
  and the cap); the pool does not divide one dossier, and no caller divides a combined answer's merged review (one part,
  one instance per review), so there it is disclosed (`over_budget`), never shortened.
- **D5 cost**: every candidate is priced per call (system text, read, output budget, at `chars_per_token`, rounded up) and
  in agent-seconds (`seconds_per_call` a call); the cheapest candidate that keeps accuracy is chosen (tokens, then seconds,
  then calls, then the method order `IN_DEPTH`, `DUPLICATE`, `SPLIT`, `N_FOLD`). One instance reading the whole response is
  the cheapest whenever it keeps accuracy, since every further call repeats the system text. When nothing keeps accuracy,
  the nearest method is taken: the most of the reviews risk calls for, then the most parts, then the cheapest.
- **D6 a combined answer** is N_FOLD (the floor's method for it): the N source reviews in parallel, each by the reviews its
  own risk calls for, then the merged review; its record carries each part's decision, and the whole-dossier candidates
  are priced and refused (`combined_needs_n_fold`). Since rules/4 (0.4.0) the service's port decides it as the pool does
  (below).
- **D7 every decision is recorded**: the features read, every candidate (its reviews, calls, tokens, seconds, whether it
  keeps accuracy, and why it was or was not chosen: `chosen`, `costlier`, `agreement_needed`, `exceeds_budget`,
  `combined_needs_n_fold`), its reasons (`in_depth_cheapest`, `agreement_risk`, `agreement_escalation`, `agreement_advised`,
  `combined_n_fold`, `split_to_fit`, `over_budget`, `size_not_measured`) and its estimated cost: in the pool plan (pool port
  1.2) as each dossier's `decision`, which the overseer validates against the request (`KIT-RT-012`) and keeps in its
  admission; in the service's plan as each transfer's method, reasons, features used and estimated cost, and in full
  (fit included) as the router's `transfer_decisions` for the request.

In the pool, then, a dossier is read whole by one instance unless risk calls for agreement (a duplicate) or it is a
combined answer (N_FOLD); a dossier whose estimated need exceeds the planned instance budget is disclosed `over_budget`,
never cut (the pack's deployer README measures which recorded dossiers fit which windows).

**The service's combined answer (rules/4, port rule 5).** Up to 0.3.0 the port priced a combined answer's synthesis as
`reviews` calls each reading the synthesis and every source whole, with no fit test and no decision: a merged review over
the instance budget (three sources of 150,000 characters, say) was planned with nothing disclosing it, against D4 and D6.
Since 0.4.0 `planner.transfer_decisions` decides every transfer first: each source by its own decision (the one its entry
is planned by, `SPLIT` where it does not fit), then the synthesis's merged review among `IN_DEPTH` and `DUPLICATE` only
(it is never divided), fit-checked, and the N_FOLD record over the sources' decisions and the merged review's
(`decision.n_fold_decision`, the pool's), with `part_decisions` naming each part's method, need, fit and reasons. The
plan is built from those records and its numbers did not change (the merged review's estimated cost is its reviews times
one call reading it whole; every plan of 6,000 generated in-contract requests is byte for byte 0.3.0's under the same
data). Router port 1.0's plan carries reasons only from the port's closed `REASON_CODES`, which have no `over_budget` and
no `split_to_fit`: the record is where a transfer one instance cannot read whole is disclosed, until a router port
version carries the code (a port change, agreed with its owner). A request naming one transfer key twice, which the
router port refuses, is refused here too (port rule 1): every transfer is one entry, and the N_FOLD decision is made once.

## 5. Rules and cost data as versioned data files

`src/epinoic_flash_router/data/MANIFEST.json` names the current files and records every file's version, release and
digest (SHA-256 of the document's canonical JSON). The current rules file (`rules-4.json`, 0.4.0) holds:

- `rules`: rules/4 in words (the decision maker D1 to D7, port rules 1 to 7, pool rules P1 to P8); rules/4 is rules/3
  with the port's N_FOLD fit-checked (D4 names the pack the system text sizes are of and the merged review no caller
  divides; D6 and port rule 5 decide the merged review by D4 and D5 and record each part; D7 says where a transfer the
  service's plan cannot disclose is disclosed), and every other section is rules/3's;
- `parameters`: `max_parts` 16, `max_reviews` 4, `hard_max_instances` 64, `context_max_bytes` 65,536 (rules-2's
  `split_words` 900 is gone: the fit replaced the word threshold);
- `pool`: `escalated_reviewers` 2, `baseline_reviewers` 1, `record_weight` 2, `batch_size` null (the pool's own
  per-instance quota), `source_reviewers` 1 and `merged_reviewers` 1 (a combined answer's parts without risk);
- `decision`: the two approaches and their methods, the criterion, the order of the choice and the methods each caller
  can run (the pool: `IN_DEPTH`, `DUPLICATE`, `N_FOLD`; the port: `IN_DEPTH`, `SPLIT`, `DUPLICATE`, `N_FOLD`);
- `signals`, `features` (the port reads `supplied_texts` and `claims` too; the pool `features`, `sources`, `merged`) and
  `methods` (the `N_FOLD` row's port entry names the merged review's fit).

The current cost data (`cost-data-4.json`, 0.4.0) holds the decision maker's prices: `chars_per_token` 4, `output_tokens`
8,000, `instance_budget_tokens` 200,000, `seconds_per_call` 30 and the dossier estimate (`base_chars` 17,000, three
characters a character of answer, 4,000 a translation), planning estimates, not measurements; and the system text of every
composition of the overseer's knowledge pack 2.1, the pack the overseer sends, as its loader builds it and its deployer
README states it (the core 249,054 characters, with the STEM module 461,507, with the translations module 345,025, with
both 557,478; `recorded.system_text_pack` names the pack), with the dossiers' recorded sizes. No price, no latency and no
model is recorded: no overseer agent has run on a model.

0.3.0's `rules-3.json` and `cost-data-3.json` stay byte for byte their 0.3.0 digests. Cost data 3 recorded pack 2.0's
system text (the core 235,694 characters, with the STEM module 448,147, with the translations module 331,665, with both
544,118) after pack 2.1, 13,360 characters larger in every composition, was installed: a dossier whose need lay within
about 3,340 tokens under the instance budget was recorded as fitting (a plain dossier of 525,000 characters: 198,174
tokens of 200,000, `in_depth_cheapest`) when one instance could not read it whole (201,514: `over_budget` with cost data
4). The decision record reaches the signed verdicts audit, so 0.4.0 released the sizes of the pack the overseer sends;
this router never imports the overseer, so holding the two together is the overseer's tests' to do.

0.2.0's `rules-2.json` and `cost-data-2.json` stay byte for byte their 0.2.0 digests; a data directory whose manifest
names them as current is planned by 0.2.0's rules (pool port 1.1, no decision record).

0.1.0 kept its rules and cost model as Python constants. They are kept as `rules-1.json` and `cost-data-1.json`, whose
digests are exactly the ones 0.1.0 reported in its identity (`177786ee…`, `228fe3e7…`).

The identity (`hello`, `pool_hello`, every plan) is `{name, version, rules_sha256, cost_data_sha256}`: the current
files' digests and this release's version. A change of a data file changes the identity by itself, so every recorded
review names the release and the rules that planned it.

## 6. The pool plan (pool rules P1 to P8)

The pool's planning decision moved here from the overseer (`epinoic_overseer.pool.plan_pool` before step 2c):

1. One entry per dossier, naming it by its position (`d1`, `d2`, … in the overseer's key order): the router never sees
   a channel uid, a task key or a fault label. Instances are numbers; the overseer names them.
2. A dossier is escalated when its task carries a repeated fault or any risk signal, or the advisor escalated it:
   `DUPLICATE` by `escalated_reviewers` distinct instances; any other dossier `IN_DEPTH`.
3. Review units: `escalated_reviewers` per escalated dossier, `record_weight` per dossier with risk records only, one
   otherwise.
4. Instances: none for an empty batch; else one, or ceil(units / batch) when more (batch = `batch_size`, or the pool's
   quota when null); at least `escalated_reviewers` when a dossier is escalated; never more than the pool's maximum
   (`capped`, with the needed instances).
5. Assignment: repeated faults first, then risk signals, then the advisor's, then the rest, each in request order; the
   least-loaded instances, ties to the lower number.
6. `over_quota` discloses an instance over the pool's quota.
7. Cheapest tier, standard profile when offered; reasons are closed codes with counts, numbers and risk classes (the
   overseer words them; a plan carries no free text); at pool port 1.2 the plan's estimated cost is the sum of its
   decisions' (absent when one is not priced).
8. At pool port 1.2 a combined answer is N_FOLD: each source by `escalated_reviewers` instances when its own transfers
   carry a repeated fault or a risk signal or the advisor escalated the dossier, else `source_reviewers`; the merged review
   by `escalated_reviewers` under the same rule for the synthesis's own transfers, else `merged_reviewers`; the sources
   need at least the sum of their reviewers at once (they run in parallel), each source on instances that review none of
   its earlier sources while there are enough; the temporary context of at most `context_max_bytes` bytes, discarded after
   the request (reason `pool_n_fold` with the count and the sources). A 1.1 request carries no combined answer.

With the released data the instances and assignments are the overseer's planner's plan, plan for plan: the overseer's
`tests/overseer_tests/test_flash_router_pool.py` holds it to all 278 recorded plans of the arena rounds r2 to r5 and r7.

## 7. Determinism, purity and the runner

The planners are pure functions of the request and the loaded data: no network, clock, randomness, process or file
access at plan time; the data are read once, at load, from the data directory only. The same request text and the same
data give the same plan text, in any process (the tests run it under two hash seeds). The runner
(`python -m epinoic_flash_router_cli`) is a separate small package so that the router package stays pure: it reads the
request from standard input and writes the answer to standard output, nothing else. Its exit statuses are 0 with the
answer, 2 when the data cannot be loaded and 3 when the request cannot be read or planned, each with its reason on
standard error and never a traceback: since 0.4.0 whatever loading the data raises is 2 and whatever reading or planning
the request raises is 3 (before it, a request nested too deep to decode raised `RecursionError` past the runner, exit 1
with a traceback; so did a zero quota and a data file nested too deep). The callers never run this runner (their own
process runner maps any failure to `KIT-RT-016`), so this concerns an operator and the tests.

## 8. What is deferred

- the fast profile (decision D30: not offered);
- `SPLIT` of one dossier in the pool (a new pool port version agreed with the overseer);
- a knowledge-pack module for the twofold instructions, so that a dossier that is no part of a combined answer is not sent
  them (about 5,150 tokens each, pack 2.0): recorded for the optimisation checks, with the cost data priced by composition
  once it exists;
- an undecided STEM check alone (`INT-SUBJ-002` with no other signal) is an agreement signal of the service's floor but
  is not among the overseer's risk classes, so neither the pool's floor nor this router's pool rules escalate on it;
  making it one is a change of the overseer's risk reading and of the pool floor's version, recorded for a decision (no
  recorded transfer carries it);
- disclosing `over_budget` (and `split_to_fit`) in the service's plan: router port 1.0's closed reason codes have neither,
  so the record (`planner.transfer_decisions`) is where they are disclosed until a router port version carries them (a
  port change, agreed with its owner; the service offers no combined mode yet, decision D33);
- the merged review's temporary context (at most `context_max_bytes`, 65,536 bytes) is in the merged review's dossier
  (the pack's deployer README) but in neither caller's read: the pool's merged part is measured from its journaled
  transfers and the port's from the synthesis and its sources, so a merged review's need can be understated by up to about
  16,384 tokens; pricing it is a change of D4's read and of recorded decisions, recorded for a decision;
- the port planner re-reads the request's supplied texts for every output: on requests far outside the router port's
  contract (thousands of outputs and texts, where the contract holds at most 17 and 16) that is quadratic work (about
  14 s at 16,000 of each, a 5 MB request); recorded with its measurements for the optimisation checks.
