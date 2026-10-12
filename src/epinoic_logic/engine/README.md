# engine — validation, compilation, decision, provenance

| Module | Purpose |
| --- | --- |
| `validator.py` | Parses untrusted JSON into a `Problem` (size and depth guards) and checks identifiers, strict sorts (no Int/Real mixing without `to_real`), policy (constant non-zero divisors; nonlinear terms off by default) and limits. Collects every diagnostic; maps E1xx/E3xx to INVALID_FORMALIZATION and E2xx to UNSUPPORTED. |
| `compiler.py` | Maps each validated node to exactly one Z3 call in a fresh `Context`; numerals from text so `0.1` is the rational 1/10; `idiv`/`mod` follow Z3 integer semantics; exports exact SMT-LIB text for audit. |
| `procedures.py` | `run_consistency`, `run_satisfiability`, `run_entailment`. Entailment checks consistency first (no vacuous proofs), then asserts premises and the negated conclusion under tracking literals so the unsat core names the premises relied on. Models are extracted exactly (`a/b`). Unknown answers are classified TIMEOUT or UNKNOWN; never success. |
| `provenance.py` | Version capture, binding digests over (problem, config, versions), HMAC-SHA256 signing and constant-time verification. |
| `runner.py` | `verify(...)`: validate → compile → decide → bind → sign. Never raises; every failure is a bound non-success result. Also lists `ungrounded_dependencies`: relied-on premises with missing, inferential, assumed or failed grounding. A definitive status that used no premise carries `E108` (vacuous). A COUNTEREXAMPLE that only reassigns a figure the problem defines but never asserts carries `E110` (unasserted figure): a premise `b <-> (n = 17)` (a Bool atom defined by a comparison of numeric symbols) whose numeric symbols no other premise mentions asserts nothing, so when the entailment, re-run with each such atom asserted, is ENTAILED, the counterexample merely sets the stated figure to another value; the diagnostic names the premise, its label, the atom and the values the counterexample chose. The status stays COUNTEREXAMPLE (the solver's answer about the encoding); the outcome layer never displays it as a verdict. `unasserted_figure_definitions(problem)` is the syntactic test (no solver) the translator shares. |
| `statuses.py`, `errors.py`, `results.py` | Closed status taxonomy with `is_definitive`, stable diagnostic codes, and result models including the scope statement. |

Resource bounds come from `SolverConfig` (per-check timeout, optional `rlimit`,
seed, optional memory budget). The memory budget is per verification while Z3's
limit is process-global, so the engine applies the budget times the number of
verifications running at once and only raises the limit while any runs; lowering
it under load made Z3 abort and the next solver call crash the process. Stress
results for this package are in `tests/stress/results/` and summarized in
`docs/STRESS_RESULTS.md`.
