# Integration contract: translator and Z3 engine

- **Contract version:** 0.1 (2026-10-12)
- **Describes code at:** commit `3147d08e0aa63d5eeaceb1072754f29e3862164d`
- **Component versions:**
  - IR `1.0`
  - engine `0.2.0`
  - policy `2026.10-v2`
  - translator `0.2.0`

  These come from `src/epinoic_logic/version.py`.

This document states what the code at that commit accepts, what it returns and what a result
establishes. Anything marked **PROPOSED** is not implemented. Every example below was produced
by running the code. Nothing here describes a deployed service: none has been deployed.

## 1. Who owns what

- **The specialist project** owns subject behaviour. It also decides when a formal check is
  relevant to a specialist's answer.
- **The translator project** owns the boundary from the supported input representation to
  explicit formal constraints and their solver results. It also owns what such a result
  establishes.
- **Neither side** should assume that an English or History claim is suitable for formal
  verification. Most interpretive claims are not.

## 2. Input: IR 1.0 problem (the engine's only input)

The engine accepts one JSON object, a `Problem` (`src/epinoic_logic/ir/schema.py`). It does
**not** accept natural language. Unknown fields are rejected.

| Field | Type | Notes |
| --- | --- | --- |
| `ir_version` | `"1.0"` | Any other value is UNSUPPORTED (E206). |
| `problem_id`, `request_id`, `claim_id` | string, 1–128 characters | Carried into the result for traceability. |
| `query` | `entailment` \| `consistency` \| `satisfiability` | `entailment` requires `conclusion`. The other two forbid it. |
| `symbols` | list of `{name, sort, meaning?, grounding?}` | `name` matches `^[a-z][a-z0-9_]{0,63}$`. `sort` is `Bool`, `Int` or `Real`. Duplicate names are rejected. |
| `premises` | list of `{id, expr, label?, grounding?, materiality?}` | `id` matches `^[A-Za-z][A-Za-z0-9_.:-]{0,127}$` and must be unique. |
| `conclusion` | same shape as a premise | Entailment only. |
| `notes` | string | Not compiled. |

**Expressions** form a closed allowlist, tagged by `op`. Any other `op` is never compiled:
- constants: `var`, `bool`, `int`, `real`;
- Boolean: `not`, `and`, `or`, `implies`, `iff`, `ite`;
- arithmetic: `add`, `sub`, `mul`, `neg`, `div`, `idiv`, `mod`, `to_real`;
- comparisons: `eq`, `ne`, `lt`, `le`, `gt`, `ge`.

**Numeric literals** are strings, so exact values survive JSON. Integers are written `"-7"`.
Reals are written `"3"`, `"-7/2"` or `"0.25"`. Floating-point values are never used.

**Not supported in IR 1.0:** quantifiers, arrays, strings, bit-vectors, uninterpreted
functions and implicit coercion. Conversion to Real must be explicit, with `to_real`.

**Policy limits,** checked before compilation (`Limits`, defaults):
- at most 64 symbols, 128 premises, 2,000 nodes;
- depth at most 40;
- at most 32 arguments to an n-ary operator;
- at most 40 digits in a constant;
- products of two non-constant terms are rejected (`allow_nonlinear = false`);
- `div`, `idiv` and `mod` need a non-zero constant divisor.

**Grounding metadata** (`kind`, `source_refs`, `certainty`, `verified`) is never compiled. The
engine only reports which relied-on premises were ungrounded or unverified.
- A payload that arrives as JSON text, bytes or a dict cannot certify itself: any
  `verified: true` it contains is discarded, with diagnostic E505.
- Only deterministic checks run in the same process may set `verified`.

### Entry points (implemented)

| Entry point | How | Notes |
| --- | --- | --- |
| Python | `epinoic_logic.engine.verify(problem_or_raw, config=SolverConfig(), limits=DEFAULT_LIMITS, signing_key=None, key_id=None)` | Never raises. Every failure becomes a result. |
| CLI | `epinoic-logic verify FILE [--timeout-ms N] [--rlimit N] [--signing-key-hex HEX --key-id ID]` | Prints the result JSON. **Exits 0 for every status**, including failures; read `status`. |
| HTTP | `POST /v1/verify`, `POST /v1/results/verify-signature`, `POST /v1/outcomes`, `GET /healthz` (`epinoic-logic serve`) | Needs `EPINOIC_SERVICE_TOKEN` and `EPINOIC_SIGNING_KEY` in the environment. Optional limits: `EPINOIC_MAX_BODY_BYTES`, `EPINOIC_MAX_CONCURRENCY`, `EPINOIC_RATE_PER_MINUTE`. The service refuses a client-supplied `memory_max_mb`. Tested in-process only; never deployed. |

## 3. Validation and solving are separate stages

`verify` runs these stages in order: validate, then compile, then decide, then bind, then
optionally sign. The result records each stage's timing.

| Stage outcome | Status | Diagnostic codes | Solver run? |
| --- | --- | --- | --- |
| Not JSON, wrong shape, unknown field or `op`, bad literal, duplicate id | INVALID_FORMALIZATION | E100–E107, E109 | no |
| Construct outside policy: nonlinear term, non-constant or zero divisor, unsupported IR version | UNSUPPORTED | E200–E206 | no |
| Unexpected exception inside the engine | INTERNAL_ERROR | E900 (exception type only, no internals) | — |

## 4. Solver outcomes

Each query maps to Z3 `check()` calls as follows. Every premise is asserted under its own
tracking literal, so an unsat core can be reported as premise ids.

| Query | Solver calls | Possible statuses |
| --- | --- | --- |
| `consistency` | premises | CONSISTENT (sat), INCONSISTENT_PREMISES (unsat), UNKNOWN, TIMEOUT |
| `satisfiability` | premises | SATISFIABLE (sat), UNSATISFIABLE (unsat), UNKNOWN, TIMEOUT |
| `entailment` | 1) premises; 2) premises and the negated conclusion | INCONSISTENT_PREMISES (the first call is unsat; the second never runs), ENTAILED (the second call is unsat), COUNTEREXAMPLE (the second call is sat), UNKNOWN, TIMEOUT |

**Consistency before entailment.** Inconsistent premises are reported as
INCONSISTENT_PREMISES, never as a vacuous ENTAILED.

**Evidence** is returned only when Z3 produced it:

| Status | Evidence field |
| --- | --- |
| COUNTEREXAMPLE | `counterexample.assignments`: exact values, with rationals written `a/b` |
| CONSISTENT, SATISFIABLE | `witness_model` |
| ENTAILED, INCONSISTENT_PREMISES, UNSATISFIABLE | `unsat_core.premise_ids` and `premises_relied_on` (when cores are enabled) |

Cores are not guaranteed minimal.

**Non-results** are UNKNOWN, TIMEOUT, UNSUPPORTED, INVALID_FORMALIZATION and INTERNAL_ERROR.
None of them is a success, and `is_definitive()` returns false for each.
- When Z3 answers `unknown`, the engine classifies it by `reason_unknown`. A reason naming a
  timeout, cancellation, resource limit or interruption becomes TIMEOUT (E400). A memory
  limit becomes UNKNOWN (E402). Anything else becomes UNKNOWN (E401).
- `reason_unknown` is kept in the result.
- The classification depends on Z3's reason text, which can change between Z3 versions.

**E108 (vacuous).** This diagnostic is added in two cases:
- ENTAILED where no premise was used, because the conclusion is a tautology;
- CONSISTENT or SATISFIABLE over zero premises.

## 5. What a result establishes

Every result carries this scope statement verbatim:

> This result concerns only the formal encoding it is bound to, under the encoded premises and
> the stated solver configuration. It does not establish that the premises are factually true,
> that the natural-language claim was translated faithfully, or that any interpretive judgement
> is correct. Grounding and semantic-fidelity information is reported separately and is advisory.

What each status means:
- **ENTAILED** means "premises ∧ ¬conclusion" is unsat, *as encoded*. It does not mean the
  English claim is true.
- **COUNTEREXAMPLE** gives one assignment satisfying the encoded premises but not the encoded
  conclusion. It does not mean the claim is false. The translation may have dropped a
  premise.
- **UNSATISFIABLE / INCONSISTENT_PREMISES** say the encoded set has no model. That is not
  proof of any other conclusion a user may want.

The verification obligation is exactly the encoded problem. It is fixed by
`binding.problem_digest`, and `binding.smt2` holds its SMT-LIB text.

**Grounding fields** report which relied-on premises are not established. They do not change
the status.
- `ungrounded_dependencies` lists premises with no grounding, or with grounding of kind
  `assumption`, `specialist_inference` or `general_knowledge`. It also lists premises that
  failed a grounding check, and quotations that were never positively checked.
- `unverified_dependencies` lists premises whose grounding is asserted but was never checked.

## 6. Provenance and integrity

Each result is bound to exactly what produced it:
- **`binding`:**
  - `problem_digest`: SHA-256 of the canonical problem;
  - `config_digest`;
  - `versions_digest`;
  - `binding_digest`;
  - `smt2`: the SMT-LIB 2 text, for audit.
- **`versions`:** `ir_version`, `engine_version`, `policy_version`, `z3_version`.
- **`solver_config`:** the configuration the solver ran with.

Changing the problem, the configuration or any version changes the binding.

**Signing.** With a key, the result carries an HMAC-SHA256 `signature` over the canonical
result and a `signature_key_id`. Tampering with any field makes `verify_signature` fail.

## 7. Resource bounds

| Setting | Default and range | Notes |
| --- | --- | --- |
| `timeout_ms` | 2,000 ms; 1–120,000 | Applies to each solver call, so entailment may take up to twice the timeout. |
| `rlimit` | none | Optional Z3 resource limit, for deterministic cut-offs. |
| `memory_max_mb` | 512; at least 128 | Z3's memory limit is process-wide. The engine therefore scales it with the number of verifications running at once and never lowers it while any run. |
| `random_seed` | 0 | |

Each verification uses a fresh Z3 context.

## 8. Examples, produced by running the baseline

The inputs are the cases in `tests/engine/test_procedures_verify.py`. They were run again
through the CLI on 2026-10-12 with z3-solver 5.1.0.0. Volatile fields are elided.

### Success: transitivity is entailed (`test_entailment_transitivity`)

Input:

```json
{"ir_version": "1.0", "problem_id": "p1", "request_id": "req1", "claim_id": "c1", "query": "entailment",
 "symbols": [{"name": "x", "sort": "Int"}, {"name": "y", "sort": "Int"}, {"name": "z", "sort": "Int"}],
 "premises": [{"id": "P1", "expr": {"op": "gt", "left": {"op": "var", "name": "x"}, "right": {"op": "var", "name": "y"}}},
              {"id": "P2", "expr": {"op": "gt", "left": {"op": "var", "name": "y"}, "right": {"op": "var", "name": "z"}}}],
 "conclusion": {"id": "C", "expr": {"op": "gt", "left": {"op": "var", "name": "x"}, "right": {"op": "var", "name": "z"}}}}
```

Output (abridged):

```json
{"query": "entailment", "status": "ENTAILED",
 "unsat_core": {"premise_ids": ["P1", "P2"], "includes_negated_conclusion": true},
 "premises_relied_on": ["P1", "P2"],
 "ungrounded_dependencies": ["P1", "P2"],
 "counterexample": null, "diagnostics": [],
 "versions": {"ir_version": "1.0", "engine_version": "0.2.0", "policy_version": "2026.10-v2", "z3_version": "5.1.0"}}
```

`ungrounded_dependencies` lists both premises because they carry no grounding metadata. The
entailment holds for the encoding only.

### Failure: a nonlinear product is UNSUPPORTED (`test_invalid_and_unsupported_payloads_become_results_not_exceptions`)

Input: a `consistency` problem over Int `x` and `y`, with a premise
`{"op": "gt", "left": {"op": "mul", "args": [x, y]}, "right": {"op": "int", "value": "0"}}`.

Output (abridged):

```json
{"query": "consistency", "status": "UNSUPPORTED",
 "diagnostics": [{"code": "E201", "message": "'mul' has 2 non-constant factors; only linear arithmetic is supported", "path": "premises[0].expr.left"}],
 "binding": {"smt2": null}, "unsat_core": null, "counterexample": null}
```

No solver call was made. The same test also shows that a payload `{"op": "exec"}` becomes
INVALID_FORMALIZATION and is never executed.

## 9. Report level: English specialist output to IR (implemented, narrower than it sounds)

Above the engine, the package turns specialist reports into IR. This translation is partial.

- **Deterministic claim extraction:** parsers for English, History and generic reports, in
  `adapters/` and `branches/`, split prose into claims with roles. Supplied texts are matched
  for quotations.
- **Deterministic IR builders:** these encode narrow sentence patterns only:
  - arithmetic statements: percentages, points, fractions, folds and absolute changes
    (`branches/quant.py`);
  - order of dated events (`branches/packs.py`);
  - Economics elasticity and Business margins;
  - cross-agent consistency of claims already formalised (`integrity/cross_check.py`).
- **Model-proposed translation:** `translate/pipeline.py` accepts a provider's JSON. It is
  parsed strictly and then validated like any other untrusted problem. A translation can come
  out AMBIGUOUS_TRANSLATION or NOT_ELIGIBLE, and those are never results.
  - The CLI (`check-report`) accepts only recorded fixture responses (`--fixtures`).
  - Anthropic and OpenAI-compatible provider classes exist. No live provider call has been
    evidenced or is claimed.
- **Router hub** (`branches.hub.RouterHub` → `channel.bus.TranslatorChannel`): it returns
  receipts carrying finding codes (INT-*, CORE-*, subject codes). **These codes are not frozen
  by this contract version.** They are still changing in active development.

## 10. PROPOSED (not implemented)

- Non-zero CLI exit codes for non-definitive statuses. Today the exit code is always 0.
- A published JSON Schema for `Problem` and `VerificationResult`, generated from the models.
- `translator_version` in `VerificationResult.versions`. Today it is reported in translation
  records, by `epinoic-logic version` and in the service's version response, but not in an
  engine result.
- A dependency lock. `pyproject.toml` gives lower bounds only: `z3-solver>=4.13`,
  `pydantic>=2.6`.
- A frozen, versioned list of report-level finding codes for the receiving side.

## 11. Changes to this contract

- A change to the IR schema bumps `IR_VERSION`.
- A change to compilation or procedures bumps `ENGINE_VERSION`.
- A change to limits or the allowlist bumps `POLICY_VERSION`.
- Each of these also bumps this contract's minor version and updates the examples.
- Field removals, or changes to status meanings, need agreement from the receiving owner before
  they merge.
