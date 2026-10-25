# engine — validation, compilation, decision, provenance

| Module | Purpose |
| --- | --- |
| `validator.py` | Parses untrusted JSON into a `Problem` (size and depth guards; a payload that is not a JSON object, a lone UTF-16 surrogate in a text or dict payload, or an integer too large to convert is `E100`, INVALID_FORMALIZATION, never an internal error: the raw-payload digest is total) and checks identifiers, strict sorts (no Int/Real mixing without `to_real`), policy (constant non-zero divisors; nonlinear terms off by default) and limits. Collects every diagnostic; maps E1xx/E3xx to INVALID_FORMALIZATION and E2xx to UNSUPPORTED. |
| `compiler.py` | Maps each validated node to exactly one Z3 call in a fresh `Context`; numerals from text so `0.1` is the rational 1/10; `idiv`/`mod` follow Z3 integer semantics; exports exact SMT-LIB text for audit. |
| `procedures.py` | `run_consistency`, `run_satisfiability`, `run_entailment`. Entailment checks consistency first (no vacuous proofs), then asserts premises and the negated conclusion under tracking literals so the unsat core names the premises relied on. The core is always extracted, whatever `produce_unsat_core` says (see "Policy evidence" below). Models are extracted exactly (`a/b`). Unknown answers are classified TIMEOUT or UNKNOWN; never success. |
| `authority.py` | Premise authority: `is_ungrounded`, `is_unverified`, `has_authority`, the dependency lists and `assumed_grounding`. Only a grounding a check in this process verified establishes a premise; every other grounding is a dependency, whatever kind it claims (see "Premise authority" below). |
| `identity.py` | The immutable identity bound into every result: `build_id` (digest of the engine, IR and version source), `schema_id` (digest of the problem, limits, configuration and result JSON Schemas) and `policy_id` (digest of `policy_manifest()`, the decision policy as data). |
| `provenance.py` | Version and identity capture, binding digests over (problem, config, versions with identity, non-default limits), HMAC-SHA256 signing and constant-time verification (`signature_matches`: total on untrusted input; a signature that is not 64 lowercase hex characters, a non-ASCII or surrogate one included, never matches and never raises, so `verify_signature` and `release_check` answer False / not eligible), `binding_inconsistencies`, and `stale_reasons` (why a result is not current-policy evidence). |
| `release.py` | `release_check(result, problem, signing_key=..., required_limits=...)`: the current-policy release check (authentic, bound, current, a positive verdict on the claim, its evidence computed, resting on established premises only). Formal entailment and permission to release stay separate. |
| `runner.py` | `verify(...)`: validate → compile → decide → bind → sign. Never raises; every failure is a bound non-success result. Also lists `ungrounded_dependencies` (relied-on premises with missing, inferential, assumed or failed grounding) and `unverified_dependencies` (relied-on premises whose task or source authority no check validated, any kind). A definitive status that used no premise carries `E108` (vacuous), and so does a COUNTEREXAMPLE over zero premises (it says only that the conclusion is no tautology: nothing the claim rests on was encoded). A COUNTEREXAMPLE over at least one premise that falsifies the conclusion only through numeric symbols no premise mentions (Z3 decides `premises AND forall free. NOT conclusion` unsat, so every premise assignment leaves a value of those figures that makes the conclusion true) carries the advisory `W111` and stands as the verdict on the encoding: the question may leave them unconstrained. It carries `E111` (unencoded reason: no verdict) only with source-linked evidence, a grounding on one of those symbols that a check in this process verified; a Bool point no premise links to stays the non sequitur COUNTEREXAMPLE, while a conclusion some premise does link to, falsified only through Bool conjuncts no premise mentions, carries the advisory `W111` ("judgement not linked", never `E111`): the claim's judgement was not encoded, and the counterexample stands as the verdict on the encoding. An ENTAILED proof whose relied-on premises restate the conclusion (it, or each of its "and" conjuncts, is syntactically a relied-on premise or a conjunct of one: `circular_premises`; compared first as canonical JSON and then in a normal form, so a trivial rewrite is still a restatement: operands of `eq` and of symmetric operators swapped, `gt`/`ge` flipped to `lt`/`le`, nested `and`/`or`/`add`/`mul` flattened and sorted, double negation removed, `x <-> true` read as `x` and `x <-> false` as `not x`, a pair of bounds `a <= b and a >= b` read as `a = b`, numerals compared as exact fractions) carries `E112` (circular) when every restating premise is the writer's own (`assumed_grounding`: an ungrounded kind or an unverified `arithmetic_fact`); restating a task setting, a rubric rule or a text is a transcription check, not a circle. A COUNTEREXAMPLE that only reassigns a figure the problem defines but never asserts (a premise `b <-> (n = 17)`, a Bool atom defined by a comparison of numeric symbols that no other premise mentions, and the entailment re-run with each such atom asserted is ENTAILED) carries the advisory `W110`: a definition is not an assertion, and "define b iff n = 17; does b necessarily hold?" is answered by exactly that counterexample, so it stands. It carries `E110` (unasserted figure: no verdict) only with source-linked evidence that a source asserts the figure, a grounding on the figure or the atom that a check in this process verified (the translation layer creates that record from the source clauses that assert the figure, read from their grammar by `translate.assertion`, `translate.coverage.apply_coverage_evidence`, so its coverage note and this code are one decision; a payload cannot carry it, E505). `E110`/`E111` take precedence over `W110`/`W111`: the unencoded-reason test runs whether or not the definition test gave the advisory `W110`, and an `E111` withholds the `W110` of the same counterexample, so a counterexample on a figure a source states is never signed as the verdict because the problem also holds a definition. Both name the premise, its label, the atom and the values the counterexample chose; neither ever instructs adding a premise because it produces entailment unless a source states it. The status stays COUNTEREXAMPLE (the solver's answer about the encoding, as it stays ENTAILED under `E112`); the outcome layer never displays any of `E108`, `E110`, `E111`, `E112` as a verdict, and shows `W110`/`W111` beside the verdict as advisory coverage warnings. `unasserted_figure_definitions(problem)` is the syntactic test (no solver) the translator shares; `source_stated_symbols(problem, names)` is the evidence test. Records and binds non-default `Limits` on every result path, and refuses over-degree polynomials under the nonlinear gate (see below). Every result, after signing, goes to the Overseer's result sink (`sink.emit`). |
| `policies.py` | Named pack policies: `PACK_POLICIES` (`linear`, `nonlinear`), `policy_limits`, `policy_config`, `required_policy`, `NONLINEAR_RLIMIT`, `NONLINEAR_MAX_DEGREE` and the polynomial-degree walk; `JOINT_LIMITS`, the integrity layer's bounds for joint problems; `NAMED_POLICIES`, `named_policy` and `named_policy_of`, the policies a caller outside the packs requests by name (the service, the CLI). |
| `sink.py` | Result sink for the Overseer. `capture_results()` opens a scope; `verify` calls `emit(signed, problem)` once per result, after signing, inside `try/except`, so every engine run made in the scope (claim outcomes, constraint bounds, branch formal checks, cross-report, attribution, entailment and paraphrase runs) is captured as canonical JSON at emit time: a later change to the live result object never reaches the capture. With no scope open, `emit` costs one `ContextVar.get` and does nothing; scopes nest, and threads and asyncio tasks never share one. Nothing here changes a result. The channel opens a scope only around an observed call (`channel/README.md`, "Observers"). |
| `statuses.py`, `errors.py`, `results.py` | Closed status taxonomy with `is_definitive`, stable diagnostic codes (`NO_VERDICT_CODES`, `ADVISORY_CODES`), and result models including the scope statement, the `limits` record, the identity in `Versions` and `Binding.limits_digest`. `parse_result(data)` is the faithful parse every receiver of a result dump uses (the service's signature and release-check routes do): a dump without `memory_max_mb` (an `exclude_none` dump of a result run with no memory budget) is read as `None`, not the default 512, so a genuine signed result still verifies after that round trip; a plain `VerificationResult.model_validate` keeps the default and would not. |

## Premise authority (`authority.py`)

A grounding kind is the proposer's claim about where a premise comes from. Only an
application-created record confers task or source authority: `grounding.verified = True`, set in
this process by a deterministic check against an immutable task field (the parsed request), a
source span (a supplied text) or an independently computed derivation. The check must verify the
premise's whole content: the translation layer's checks (`translate.relations`) validate a premise
that relates symbols (`speed = d / 8`) only when a record states that relation, never because its
figures occur in a record, so a model-invented relation stays in `unverified_dependencies` whatever
its kind. A payload that arrives as data cannot set it (`E505`; the service refuses it outright).

| Grounding of a relied-on premise | Listed in |
| --- | --- |
| none, `assumption`, `specialist_inference`, `general_knowledge`, `verified = False`, an unverified `quotation` | `ungrounded_dependencies` |
| any other kind with `verified` unset, `arithmetic_fact`, `task_setting` and `rubric_rule` included | `unverified_dependencies` |
| any kind except the writer's own steps, with `verified = True` from a check in this process | neither: established |

Until the external review of 2026-10-12 an unchecked `arithmetic_fact`, `task_setting` or
`rubric_rule` was listed nowhere, so a translation could hide an invented premise (160 km for a
supplied 120 km) by choosing that label. The lists never change a status: formal entailment from
an unverified premise is still ENTAILED, and `release.release_check` refuses it.

## Policy evidence is computed, not optional

The unsat core is always extracted (the tracking literals are assumptions, so Z3 has it at no
extra cost). `premises_relied_on`, the dependency lists, `E108` and `E112` rest on it.
`SolverConfig.produce_unsat_core` only decides whether the raw `unsat_core` record is serialised.
Before 0.4.0 the flag also emptied the dependency lists and skipped `E108`, so a premise-free
tautology became a displayed ENTAILED with the flag off: "not computed" read as "no
dependencies". Toggling the flag now changes no dependency, no diagnostic and no release check,
through the engine and through the HTTP service.

## Current-policy identity, staleness and the release check

Every result binds `Versions.build_id`, `schema_id` and `policy_id` (`identity.py`) beside the
component versions, so a result issued by another build is never current, even when someone
forgot to bump a version string. `provenance.stale_reasons(result, required_limits=...)` says why
a result is not current-policy evidence: other versions or identity (or none: a result issued
before identities were bound), or validation limits other than those the receiver requires.
Such a result stays inspectable: it parses, re-serialises byte-identically and its signature
still verifies. It cannot satisfy a current-policy check (`release.release_check`,
`integrity.handoff.check_result_binding`, the outcome composer) until the problem is verified
again. `tests/engine/data/` holds genuine signed results of releases 0.2.0 and 0.3.0 for the
upgrade tests.

Resource bounds come from `SolverConfig` (per-check timeout, optional `rlimit`,
seed, optional memory budget). The memory budget is per verification while Z3's
limit is process-global, so the engine applies the budget times the number of
verifications running at once and only raises the limit while any runs; lowering
it under load made Z3 abort and the next solver call crash the process. Stress
results for this package are in `tests/stress/results/` and summarized in
`docs/STRESS_RESULTS.md`.

## Named pack policies (`policies.py`)

An integrity pack never passes raw `Limits` to the engine. Its formal check names a policy,
and the engine maps the name to a fixed value:

| Policy | `Limits` | Solver configuration (`policy_config`) |
| --- | --- | --- |
| `linear` | `DEFAULT_LIMITS`, the same object every existing caller uses | the caller's configuration, unchanged |
| `nonlinear` | `Limits(allow_nonlinear=True)`; every other field is the default | the caller's configuration with `rlimit = min(caller's rlimit, NONLINEAR_RLIMIT)` |

- `PACK_POLICIES` is a read-only mapping and `Limits` is frozen. A pack can name a policy. It
  cannot add one, replace one, or raise `max_symbols`, `max_premises`, `max_nodes`,
  `max_depth`, `max_nary_args` or `max_const_digits`, and it cannot change the division
  rules.
- Names are matched exactly. Case variants, surrounding whitespace, confusable characters,
  `str` subclasses and non-strings all raise `UnknownPolicyError` (a `ValueError`). The
  error message is bounded and never calls a foreign `__repr__`. A check with an unknown
  policy must be reported as undecided; it is never run under another policy.
- `required_policy(problem)` returns `"nonlinear"` exactly when the linear policy refuses the
  problem with `E201`. A pack can use it to choose the least permissive policy.

**Named policies a caller may request.** `NAMED_POLICIES` (read-only) is the pack policies plus
`joint`, the integrity layer's `JOINT_LIMITS`: the names a caller outside the packs may give
(`POST /v1/verify` and the release check's `policy`, `epinoic-logic verify --policy`). It never
sends limits of its own. `named_policy(name, config)` returns the `Limits` and the solver
configuration exactly as the in-process caller of that policy uses them (a pack policy as the
channel runs a branch check, `policy_limits` and `policy_config`; `joint` as the cross-agent joint
checks run, `JOINT_LIMITS` with the configuration unchanged), so the same problem gets the same
decision, and the same binding, in process and over HTTP. Names are matched as strictly as pack
policy names; anything else raises `UnknownPolicyError`. `named_policy_of(limits)` names the
policy a result's `limits` record stands for (`None` is `linear`; limits no named policy has name
none), comparing every limit value, so a receiver replaying a pipeline problem over HTTP can name
the policy the pipeline used. A pack still cannot choose `joint` (`policy_limits("joint")` raises),
and the table is part of the policy identity (`policy_manifest()["named_policies"]`).

**Signed and bound record.** When the `Limits` a problem was validated under differ from
`DEFAULT_LIMITS`, `VerificationResult.limits` records them on every result path, before
signing. That includes the nonlinear policy, and other callers too (the cross-report pool's
`JOINT_LIMITS`). The signature covers the record, and since 0.4.0 the binding does too:
- changing it, stripping it, or adding one to a default result fails `verify_signature`;
- `Binding.limits_digest` is the digest of the non-default limits, appended to the binding
  digest (`sha256(problem|config|versions|limits)`), so a permissive result never shares a
  binding with a default one; the default formula (`sha256(problem|config|versions)`) is
  unchanged, and the default limits themselves are part of the bound policy identity;
- the hand-off binding check and the release check compare the bound limits with the policy
  the receiver requires (`limits=` / `required_limits=`, default `DEFAULT_LIMITS`); a joint
  result is checked against `JOINT_LIMITS`. This is separate from the version identity: two
  policies used within one build are told apart by the limits digest alone.

With the default `Limits` the record and the digest are `None` and wrap serializers leave them
out of every dump, so a result of the old shape (and its signature) still serialises
byte-identically (golden digests in `tests/engine/test_pack_policies.py`). A `limits` argument
that is not a `Limits` instance is an INTERNAL_ERROR result. The engine never guesses bounds.

**Degree bound under the nonlinear gate.** With nonlinear terms allowed, the runner refuses any
assertion whose polynomial degree exceeds `NONLINEAR_MAX_DEGREE` = 24. The result is UNSUPPORTED
(`E201`, with the assertion's path), returned before compilation. The degree walk is iterative
and counts:
- `mul` as the sum of its factors' degrees;
- divisors;
- `ite` conditions.

It is an upper bound. The bound exists because Z3 cannot be interrupted inside some
high-degree polynomial operations. With a 2000 ms timeout, `x^n = 2` measured:

| n | 24 | 32 | 64 to 256 | 384 | 512 | 768 | 1024 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wall time | 0.25 s, decided | 0.64 s, decided | 2.0 to 2.15 s, TIMEOUT | 2.3 s | 3.6 s | 7.0 s | 20.7 s |

`rlimit` did not shorten those runs. STEM needs degree 13 at most. Under the linear gate every
degree is at most 1, so the bound never applies there.

**`NONLINEAR_RLIMIT` = 2,000,000.** This is the per-call Z3 resource limit, so a nonlinear
cutoff falls at the same point on every run. Z3 5.1.0 reports it as `canceled`, which the
engine classifies as TIMEOUT (`E400`), never a success. Calibration, measured with
`tests/engine/test_stem_shapes.py`:
- **STEM shapes.** Every shape of `docs/STEM_DESIGN.md` sections 5 and 7 needs at most 7,318
  units (`rearrangement_root_fail`). The linear shapes need 84 to 711 units. The suite asserts
  that every nonlinear shape still decides at `NONLINEAR_RLIMIT // 10`, a tenfold headroom.
- **Hard systems.** Cubic systems over the integers with no solution (a³ + b³ = c³ with a, b,
  c > 1, and x³ = 2y³) are cut off after 0.3 to 0.5 s, even under a 60 s timeout. The status
  and reason are the same on every run.
- **Limitation.** The rlimit is deterministic only where Z3 counts resource steadily. In
  nonlinear real projection, for example a chain of auxiliaries `y_k = y_{k-1}²` that keeps
  each assertion at degree 2, Z3 counts slowly. There the wall-clock timeout stops the run
  first: a 5-link chain stopped at 2.2 s under 2000 ms, and a 63-link chain at 3.8 s. Such
  cutoffs are still TIMEOUT, never a success.
- **Nested roots hit the same limitation.** A STEM check can produce such a chain: √√√√2 written
  with exact `sq` auxiliaries is one. Depth 2 or 3 decides in about 30 to 50 ms when the value is
  right. Depth 4 and deeper (measured up to 12) runs to the wall-clock timeout, 2.0 s under
  2000 ms, with or without a wrong value. So each such check costs a full timeout, and only the
  bus's per-report budget bounds the total. The checks stage should cap exact nested roots at
  depth 3 and read deeper ones through enclosures (linear) or report them undecided.
- **Model building is outside every bound.** The procedures check under tracking assumptions
  (for unsat cores), which sends nonlinear problems through Z3's incremental core. There, once
  `check` has returned, `get_model` is not covered by the timeout or the rlimit. A wrong
  depth-3 nested root took 1.24 s in all:
  - 0.43 s in `check`;
  - 0.73 s in two `get_model` calls with irrational values. One of them builds the model of the
    entailment's consistency precheck, and `run_entailment` then discards it.

  Checked without assumptions, the same problem takes 11 ms (`check`) plus under 1 ms (model),
  and depth 4 decides in 0.8 s instead of timing out. Two changes are recommended for
  `procedures.py`, which is outside stage `engine`:
  - skip model extraction in the entailment precheck;
  - for nonlinear problems, decide first without assumptions and compute the core only on an
    unsat answer.

**Measured cost of the STEM shapes** (median of 3 runs): 3 to 19 ms each, with one exception.
Z3 takes 100 to 180 ms to find the *smaller* root of a quadratic such as x² − 3x + 1 inside a
narrow interval (0.38, 0.46 and 0.21 are slow), while using only about 1,900 rlimit units.
Larger roots, surds and wrong roots take 2 to 15 ms. A linear sign-change form (p(lo) and p(hi)
of opposite signs, by the intermediate value theorem) decides the same correct root in about
13 ms. A double root has no sign change, so the nonlinear Form S stays the fallback. Both
forms are pinned in the shape tests.
