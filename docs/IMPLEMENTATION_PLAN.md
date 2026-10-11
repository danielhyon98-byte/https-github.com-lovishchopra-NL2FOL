# Implementation Plan — Epinoic AI Logic Translator and Z3 Verification Engine

**Status: PROVISIONAL.** Derived from the context pack and kickoff prompt only. The
governing specifications (`02_Z3_…`, `03_Overseer_…`) and the IB training pack are
missing (see `docs/context-pack/MISSING_FILES.md`); every phase must be reconciled
against them when they arrive. Per-component status lives in `docs/STATUS.md`.
Nothing is deployed.

## Architecture

```
student browser
   │  HTTPS (no solver access, no provider keys)
   ▼
Cloudflare Worker (edge): auth, quotas, size limits, request ids   [planned, not in this repo]
   │  authenticated service call (bearer token; private binding)
   ▼
Solver service (this repository, native Python + Z3)                [implemented, not deployed]
   specialist report ──► adapter ──► claim records
   claim ──► eligibility (role/kind rules + IB subject policy)
         ──► translator (replaceable provider) ──► strict JSON ──► IR 1.0 (data)
         ──► grounding checks (quotations verbatim vs supplied text)
         ──► validator ──► compiler ──► Z3 procedures (consistency first)
         ──► result bound to (problem, config, versions) and HMAC-signed
         ──► outcome (display status + plain-language summary + scope statement)
   ▼
Overseer: verifies signature, reads display status, never trusts agent self-reports   [contract only]
```

Three correctness dimensions are kept separate: **structural** (deterministic code:
schema, ids, hashes, grounding, structural findings), **semantic fidelity**
(advisory review of the translation, never a verification), **formal validity**
(engine verdict about the encoded problem only).

## Status taxonomy (closed)

| Status | Meaning | Definitive |
| --- | --- | --- |
| ENTAILED | premises consistent and premises ∧ ¬conclusion unsatisfiable | yes |
| COUNTEREXAMPLE | premises consistent; an exact assignment satisfies them and falsifies the conclusion | yes |
| INCONSISTENT_PREMISES | premises alone unsatisfiable; core names the conflicting premises | yes |
| CONSISTENT / SATISFIABLE / UNSATISFIABLE | query results with witness or core | yes |
| UNKNOWN, TIMEOUT | solver gave up or hit its bound | no |
| UNSUPPORTED, INVALID_FORMALIZATION | policy or schema rejection, with diagnostics | no |
| AMBIGUOUS_TRANSLATION, NOT_ELIGIBLE | translation-layer outcomes | no |
| INTERNAL_ERROR | failure; generic message only | no |

No status means the natural-language claim is true. Every result carries the scope
statement saying so.

## Phases

| # | Phase | Purpose | Status |
| --- | --- | --- | --- |
| 0 | Reconcile with missing specifications | Align contracts, statuses, eligibility and Overseer behaviour with `02`/`03` and the IB pack | blocked on documents |
| 1 | Shared contracts | IR 1.0, statuses, results, claim/report contracts, subject profiles | implemented, tested |
| 2 | Verification engine | validator, compiler, procedures, provenance, runner | implemented, tested (35 tests) |
| 3 | Translation layer | eligibility + subject policy, grounding, strict parsing, prompts, providers (fixture; model-backed untested live), pipeline, advisory review, outcome | in progress |
| 4 | Specialist adapters | generic structured adapter (integration contract for all specialists); English specialist adapter as worked example; multi-subject fixtures | in progress |
| 5 | Service boundary and CLI | FastAPI with bearer auth, body/concurrency/rate limits, signed results, self-certification rejection | in progress |
| 6 | Overseer QA loop | independent overseer agents test the program on the English corpus and mutations; fixers apply feedback until clean | in progress |
| 7 | Overseer and combinator integration | signed-result verification, claim ledger hooks, display rules, conflict visibility | planned; needs `03` and the Epinoic codebase |
| 8 | Cloudflare deployment | TypeScript Worker edge → Container (or external) solver service; Queues for background jobs; D1 for task/claim metadata; R2 for documents | planned; needs account and plan facts |
| 9 | Observability and load tests | request/claim ids, per-stage latency, timeouts, retries, result categories, error types; ramp/burst/sustained load | planned |
| 10 | Live provider integration and fidelity evaluation | run model-backed translation and review against an evaluation set; measure fidelity and cost | planned; needs credentials |

Each phase's acceptance criteria: its tests pass; no non-success status can be shown
as success; results are bound and signed; documentation updated; limitations stated.

## Testing matrix (kickoff categories → tests)

| Category | Where |
| --- | --- |
| AST validation and compilation; unsupported operations; malformed or malicious ASTs | `tests/engine/test_validator.py`, `tests/engine/test_compiler.py` |
| Satisfiable/unsatisfiable premises; entailment; counterexample; inconsistent premises; timeout and error handling | `tests/engine/test_procedures_verify.py` |
| Source provenance; modified representation invalidates old results | `tests/engine/test_procedures_verify.py` (binding), adapters e2e (in progress) |
| Agent self-certification attempts | service tests and e2e (in progress) |
| End-to-end through the service boundary | `tests/service/` (in progress) |
| Translation: eligibility, grounding, ambiguity, provider failure | `tests/translate/` (in progress) |
| Specialist outputs: genuine and corrupted English examples; other subjects | `tests/e2e/` and the overseer QA loop (in progress) |

## Limits and budgets

| Control | Default | Where |
| --- | --- | --- |
| Solver timeout | 2000 ms per check (entailment runs two checks) | `SolverConfig.timeout_ms` |
| Deterministic cutoff | `rlimit` optional | `SolverConfig.rlimit` |
| Problem shape | 64 symbols, 128 premises, 2000 nodes, depth 40, 32 n-ary args, 40-digit numerals | `ir.schema.Limits` |
| Payload | 1 MB | `parse_and_validate`, service settings |
| Concurrency / rate | 4 concurrent verifications; 60 requests per minute per token | service settings |
| Translation attempts | 2 | `Translator.max_attempts` |
| Edge limits to respect later | 128 MB isolate, 1 s startup, CPU 30 s default (Paid) | Cloudflare docs source |

## Known limitations

- Proves properties of the encoding under its premises; never the truth of premises, the fidelity of translation, or any interpretive judgement.
- v1 formal subset: propositional logic and linear integer/real arithmetic with constant divisors. Nonlinear terms, quantifiers, units, strings and symbolic calculus are UNSUPPORTED.
- Eligibility and subject profiles are heuristic working configuration pending the IB material.
- Model-backed providers are untested live; the English parser is heuristic; grounding checks cover quotations only.
- Not a universal hallucination detector; it makes unsupported inferences, invented quotations and contradictions visible.

## Open questions for the missing specifications

Exact status names and fields; required Overseer decision rules; claim-id scheme and ledger format; which subjects and claim classes are in scope first; prompt and provider requirements; data-retention rules for student text.
