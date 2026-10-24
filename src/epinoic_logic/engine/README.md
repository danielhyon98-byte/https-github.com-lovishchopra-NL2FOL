# engine — validation, compilation, decision, provenance

| Module | Purpose |
| --- | --- |
| `validator.py` | Parses untrusted JSON into a `Problem` (size and depth guards) and checks identifiers, strict sorts (no Int/Real mixing without `to_real`), policy (constant non-zero divisors; nonlinear terms off by default) and limits. Collects every diagnostic; maps E1xx/E3xx to INVALID_FORMALIZATION and E2xx to UNSUPPORTED. |
| `compiler.py` | Maps each validated node to exactly one Z3 call in a fresh `Context`; numerals from text so `0.1` is the rational 1/10; `idiv`/`mod` follow Z3 integer semantics; exports exact SMT-LIB text for audit. |
| `procedures.py` | `run_consistency`, `run_satisfiability`, `run_entailment`. Entailment checks consistency first (no vacuous proofs), then asserts premises and the negated conclusion under tracking literals so the unsat core names the premises relied on. Models are extracted exactly (`a/b`). Unknown answers are classified TIMEOUT or UNKNOWN; never success. |
| `provenance.py` | Version capture, binding digests over (problem, config, versions), HMAC-SHA256 signing and constant-time verification. |
| `runner.py` | `verify(...)`: validate → compile → decide → bind → sign. Never raises; every failure is a bound non-success result. Also lists `ungrounded_dependencies`: relied-on premises with missing, inferential, assumed or failed grounding. A definitive status that used no premise carries `E108` (vacuous), and so does a COUNTEREXAMPLE over zero premises (it says only that the conclusion is no tautology: nothing the claim rests on was encoded). A COUNTEREXAMPLE over at least one premise that falsifies the conclusion only through numeric symbols no premise mentions carries `E111` (unencoded reason: Z3 decides `premises AND forall free. NOT conclusion` unsat, so every premise assignment leaves a value of those figures that makes the conclusion true; the claim's own reason was not encoded); a Bool point no premise links to stays the non sequitur COUNTEREXAMPLE. An ENTAILED proof whose relied-on premises restate the conclusion (it, or each of its "and" conjuncts, is syntactically a relied-on premise or a conjunct of one: `circular_premises`) carries `E112` (circular) when every restating premise is the writer's own (`assumed_grounding`: an ungrounded kind or an unverified `arithmetic_fact`); restating a task setting, a rubric rule or a text is a transcription check, not a circle. A COUNTEREXAMPLE that only reassigns a figure the problem defines but never asserts carries `E110` (unasserted figure): a premise `b <-> (n = 17)` (a Bool atom defined by a comparison of numeric symbols) whose numeric symbols no other premise mentions asserts nothing, so when the entailment, re-run with each such atom asserted, is ENTAILED, the counterexample merely sets the stated figure to another value; the diagnostic names the premise, its label, the atom and the values the counterexample chose. The status stays COUNTEREXAMPLE (the solver's answer about the encoding, as it stays ENTAILED under `E112`); the outcome layer never displays any of `E108`, `E110`, `E111`, `E112` as a verdict. `unasserted_figure_definitions(problem)` is the syntactic test (no solver) the translator shares. Records non-default `Limits` on every result path, and refuses over-degree polynomials under the nonlinear gate (see below). Every result, after signing, goes to the Overseer's result sink (`sink.emit`). |
| `policies.py` | Named pack policies: `PACK_POLICIES` (`linear`, `nonlinear`), `policy_limits`, `policy_config`, `required_policy`, `NONLINEAR_RLIMIT`, `NONLINEAR_MAX_DEGREE` and the polynomial-degree walk. |
| `sink.py` | Result sink for the Overseer. `capture_results()` opens a scope; `verify` calls `emit(signed, problem)` once per result, after signing, inside `try/except`, so every engine run made in the scope (claim outcomes, constraint bounds, branch formal checks, cross-report, attribution, entailment and paraphrase runs) is captured as canonical JSON at emit time: a later change to the live result object never reaches the capture. With no scope open, `emit` costs one `ContextVar.get` and does nothing; scopes nest, and threads and asyncio tasks never share one. Nothing here changes a result. The channel opens a scope only around an observed call (`channel/README.md`, "Observers"). |
| `statuses.py`, `errors.py`, `results.py` | Closed status taxonomy with `is_definitive`, stable diagnostic codes, and result models including the scope statement and the `limits` record. |

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

**Signed record.** When the `Limits` a problem was validated under differ from
`DEFAULT_LIMITS`, `VerificationResult.limits` records them on every result path, before
signing. That includes the nonlinear policy, and other callers too (the cross-report pool's
`JOINT_LIMITS`). The signature therefore covers the record:
- changing it, stripping it, or adding one to a default result fails `verify_signature`;
- the binding formula (`sha256(problem|config|versions)`) and the hand-off binding check are
  unchanged.

With the default `Limits` the field is `None` and a wrap serializer leaves it out of every
dump. Default results, their signable text and their signatures are byte-identical to the
committed model (golden digests in `tests/engine/test_pack_policies.py`). A `limits` argument
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
