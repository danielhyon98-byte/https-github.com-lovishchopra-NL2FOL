# Flash router design (`epinoic-flash-router` 0.2.0)

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
| the overseer pool (section 7b, pool port 1.1) | `pool_hello`, `pool_plan` | `pool-router-hello.v1`, `pool-routing-request.v1` → `pool-routing-plan.v1` | `minimum-oversight-floor/pool-1` (the overseer's `floor.py`) |

The overseer pool attaches the router **by capability**: only a router whose module exposes `pool_hello()` and
`pool_plan()` and whose pool hello declares the capability `pool-plan` at a pool port version the overseer speaks (1.1)
is attached; any other is refused with `KIT-RT-015` (a failing one `KIT-RT-016`) and the overseer's floor plan runs. The
service attaches it by `EPINOIC_FLASH_ROUTER`. Neither the translator nor the overseer imports this package.

## 3. The minimum-oversight floor, and why accuracy never depends on this router

Agent self-reports and routing advice are advisory. Each caller computes its own deterministic floor from the same risk
signals the router reads, validates the router's plan as untrusted data, and runs it only when it is in contract and at
or above the floor; otherwise the floor plan runs and the refusal is recorded (`KIT-RT-020` below the floor, the
contract's own `KIT-RT` codes otherwise). With no router attached the floor plan runs. Risk signals only escalate. So a
re-tuned or weakened data file, or an edited planner, can add oversight but never remove it.

The pool's floor (`minimum-oversight-floor/pool-1`, in the overseer): every dossier of a batch is reviewed by at least
one instance; a dossier whose task carries a repeated fault or a risk signal (an error-level finding, a rejection, a
contradiction, an encoding conflict, a withheld verdict, a named defect at warning or error, an unchecked source or a
STEM method error at that severity, an argument diagnosis that did not finish), or that the overseer's escalation
advisor escalated, is reviewed by at least two distinct instances; no plan grows past the pool's maximum; every instance
runs on the cheapest tier from the pool's one pack. A combined answer's floor becomes N_FOLD when combined answers reach
the pool (architecture step 3). What lies above the floor is this router's choice: the batch sizes (how many instances
a batch is spread over), the weight of risk records, extra duplicates, the profile.

## 4. The method table

| Method | Meaning | Complete reviews | Port plan (rules/2) | Pool plan (rules/2, pool port 1.1) |
|---|---|---|---|---|
| `IN_DEPTH` | one instance examines the whole response | 1 | one review, one part | a dossier that is not escalated |
| `SPLIT` | the work divided across parallel instances, each part reviewed once | 1 | a long output read by one review | not for one dossier; a batch over the quota is spread over instances |
| `DUPLICATE` | independent duplicate reviews, combined by the verdict combination | `reviews` | two or more reviews | an escalated dossier, `escalated_reviewers` instances |
| `N_FOLD` | a combined answer's sources each reviewed, then one merged review over all of them | `reviews` | a combined answer's synthesis | step 3 |

The table is data (`methods` in the rules file), ready for a cost planner later: a planner that divides one dossier
(`SPLIT`) or reviews a combined answer in the pool (`N_FOLD`) is a new pool port version agreed with the overseer.

## 5. Rules and cost data as versioned data files

`src/epinoic_flash_router/data/MANIFEST.json` names the current files and records every file's version, release and
digest (SHA-256 of the document's canonical JSON). The current rules file (`rules-2.json`) holds:

- `rules`: rules/2 in words (port rules 1 to 7, pool rules P1 to P7);
- `parameters` (the port planner's thresholds and batch sizes): `split_words` 900, `max_parts` 16, `max_reviews` 4,
  `hard_max_instances` 64, `context_max_bytes` 65,536;
- `pool` (the pool planner's thresholds and batch size): `escalated_reviewers` 2, `baseline_reviewers` 1,
  `record_weight` 2, `batch_size` null (the pool's own per-instance quota, as the overseer's planner sized batches);
- `signals`: the agreement signals the port rules read (negative statuses, undecided statuses, the STEM undecided code);
- `features`: the features each planner reads (`port`, `port_combined`, `pool`, `pool_limits`);
- `methods`: the method table above.

The current cost data (`cost-data-2.json`) holds the port plan's planning estimates (`review_tokens_base` 6,000 tokens,
`chars_per_token` 4, `seconds_per_instance` 30: estimates, not measurements) and the sizes the overseer recorded for its
knowledge pack 1.5 and its dossiers (system text per module, dossier sizes, the largest needs per module, the output
budget), measured by the overseer's exporter on the recorded rounds with no model called. No price, no latency and no
model is recorded: no overseer agent has run on a model. The cost planner is deferred (no optimisation before the bug
testing is done), so a pool plan estimates no cost and the recorded sizes wait for it.

0.1.0 kept its rules and cost model as Python constants. They are kept as `rules-1.json` and `cost-data-1.json`, whose
digests are exactly the ones 0.1.0 reported in its identity (`177786ee…`, `228fe3e7…`).

The identity (`hello`, `pool_hello`, every plan) is `{name, version, rules_sha256, cost_data_sha256}`: the current
files' digests and this release's version. A change of a data file changes the identity by itself, so every recorded
review names the release and the rules that planned it.

## 6. The pool plan (pool rules P1 to P7)

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
   overseer words them; a plan carries no free text); no cost estimate.

With the released data this is the overseer's planner's plan, plan for plan: the overseer's
`tests/overseer_tests/test_flash_router_pool.py` holds it to all 278 recorded plans of the arena rounds r2 to r5 and r7.

## 7. Determinism, purity and the runner

The planners are pure functions of the request and the loaded data: no network, clock, randomness, process or file
access at plan time; the data are read once, at load, from the data directory only. The same request text and the same
data give the same plan text, in any process (the tests run it under two hash seeds). The runner
(`python -m epinoic_flash_router_cli`) is a separate small package so that the router package stays pure: it reads the
request from standard input and writes the answer to standard output, nothing else.

## 8. What is deferred

- the cost planner and the fast profile (no optimisation this week): the method table and the recorded sizes are ready;
- `SPLIT` of one dossier and `N_FOLD` in the pool (a new pool port version; `N_FOLD` with step 3);
- an undecided STEM check alone (`INT-SUBJ-002` with no other signal) is an agreement signal of the service's floor but
  is not among the overseer's risk classes, so neither the pool's floor nor this router's pool rules escalate on it;
  making it one is a change of the overseer's risk reading and of the pool floor's version, recorded for a decision (no
  recorded transfer carries it).
