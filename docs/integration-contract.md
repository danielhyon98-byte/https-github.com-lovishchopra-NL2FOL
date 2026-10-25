# Integration contract: translator and Z3 engine

- **Contract version:** 0.4 (2026-10-17). Version 0.1 described commit
  `3147d08e0aa63d5eeaceb1072754f29e3862164d` (engine `0.2.0`); 0.2 describes the engine fixes of
  the external review of 12 October 2026; 0.3 adds the named engine policy a caller requests over
  HTTP and on the command line, after the end-to-end simulation of 16 October 2026 (the component
  versions are unchanged by 0.3); 0.4 adds the named diagnostics of the argument diagnosis
  (section 10). Section 12 lists what changed.
- **Component versions:**
  - IR `1.0`
  - engine `0.5.0`
  - policy `2026.10-v5`
  - translator `0.5.1`
  - argument-diagnosis rules `argdiag-2` (`ARG_RULES_VERSION`)

  These come from `src/epinoic_logic/version.py`. Every result also binds the immutable identity
  of the build that produced it (`build_id`, `schema_id`, `policy_id`; section 6).

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

**Named policies** (`engine.policies.NAMED_POLICIES`): a caller that is not an in-process pack may
ask for a problem to be decided under one of three named policies, and never under limits of its
own. `linear` is the default limits above. `nonlinear` is the default limits with
`allow_nonlinear = true` and the solver's `rlimit` capped at `NONLINEAR_RLIMIT` (2,000,000; a lower
`rlimit` is kept), as the channel's STEM checks run; assertions above polynomial degree 24 are
UNSUPPORTED (E201). `joint` is the integrity layer's joint bounds (at most 1,024 symbols, 4,096
premises, 200,000 nodes, depth 40, 64 arguments; no nonlinear terms), as the cross-agent joint
checks run. `engine.policies.named_policy(name, config)` gives the limits and configuration for a
name, exactly as the in-process caller of that policy uses them; an unknown name raises
`UnknownPolicyError` and nothing is run.

**Grounding metadata** (`kind`, `source_refs`, `certainty`, `verified`) is never compiled. The
engine only reports which relied-on premises were ungrounded or unverified.
- A payload cannot certify itself. The two entry points handle a `verified: true` in it two ways,
  both pinned by `tests/service/test_e505_contract_b15.py`:
  - **in process** (`engine.verify` on JSON text, bytes or a dict): the assertion is discarded,
    with diagnostic E505, and the premise it meant to certify stays an unverified dependency; the
    verdict on the encoding is unchanged;
  - **over HTTP** (`POST /v1/verify`): the request is refused with 400 E505 before anything runs
    (no result, no solver call), whether the key stands at the top of the envelope, in the problem
    or nested as `grounding.verified: true`. This is stricter than the in-process discard, and it is
    kept: a remote caller gets no result built from a body that tried to certify itself.
- Only deterministic checks run in the same process may set `verified`. Only such a record
  confers task or source authority: a `kind` is the proposer's claim, never a validation.

### Entry points (implemented)

| Entry point | How | Notes |
| --- | --- | --- |
| Python | `epinoic_logic.engine.verify(problem_or_raw, config=SolverConfig(), limits=DEFAULT_LIMITS, signing_key=None, key_id=None, *, diagnose=True, severity_cap=None)` | Never raises. Every failure becomes a result. `diagnose` and `severity_cap` (section 10) are Python keywords only: neither HTTP nor `SolverConfig` reaches them. |
| CLI | `epinoic-logic verify FILE [--timeout-ms N] [--rlimit N] [--policy NAME] [--signing-key-file PATH \| --signing-key-env [VAR] \| --signing-key-hex HEX] [--key-id ID]` | Prints the result JSON. **Exits 0 for every status**, including failures; read `status`. `--policy` is `linear` (default), `nonlinear` or `joint`; an unknown name exits 2 with a JSON error. A signing key is hex text of at least 16 bytes (the service's floor); a shorter one, or more than one key source, is a usage error (exit 2), and the key is never echoed. `--signing-key-file` (the hex text on its first line) and `--signing-key-env` (by default `EPINOIC_SIGNING_KEY`, the service's variable) keep the key off the command line, where `--signing-key-hex` exposes it in the process list. |
| HTTP | `POST /v1/verify`, `POST /v1/results/verify-signature`, `POST /v1/results/release-check`, `POST /v1/outcomes`, `GET /healthz` (`epinoic-logic serve`) | Needs `EPINOIC_SERVICE_TOKEN` and `EPINOIC_SIGNING_KEY` in the environment. Optional limits: `EPINOIC_MAX_BODY_BYTES`, `EPINOIC_MAX_CONCURRENCY`, `EPINOIC_RATE_PER_MINUTE`. The service refuses a client-supplied `memory_max_mb` or `model_completion` (400 E100: both are server-controlled, and models are always completed), validates `config` strictly (`"100"` is no integer), refuses a body holding a lone surrogate escape on every route (400 E100), takes client fixture responses on `POST /v1/outcomes` only when `allow_client_fixtures` is set (otherwise 403 E506), and refuses a self-certifying body (`verified: true` anywhere in the problem, or a self-certification key in the envelope) with 400 E505 before anything runs, where the Python entry point discards the assertion with an E505 diagnostic (both above). `POST /v1/verify` takes `{problem, config?, policy?}`: `policy` names a named policy (above; `linear` by default), anything else is HTTP 400 `E100` before anything runs, and authentication, the rate limit, the body-size limit (which bounds the problem size under every policy) and the concurrency limit apply unchanged; the release check takes the same names as its required policy. Tested in-process and over a local socket in the test suite; never deployed. |

## 3. Validation and solving are separate stages

`verify` runs these stages in order: validate, then compile, then decide, then diagnose, then
bind, then optionally sign. Diagnose is the argument diagnosis of section 10. It runs on every
problem that reaches the solver, unless the caller passes `diagnose=False`. The result records
each stage's timing.

| Stage outcome | Status | Diagnostic codes | Solver run? |
| --- | --- | --- | --- |
| Not JSON, wrong shape, unknown field or `op`, bad literal, duplicate id | INVALID_FORMALIZATION | E100–E107, E109 | no |
| Construct outside policy: nonlinear term, non-constant or zero divisor, unsupported IR version | UNSUPPORTED | E200–E206 | no |
| Exact arithmetic whose numbers could exceed `MAX_COEFFICIENT_DIGITS` (16,000 digits, a bound read from the IR's numerals: `policies.coefficient_digits`) | INVALID_FORMALIZATION | E307 | no |
| Under a policy that allows nonlinear terms, products that force values of more than `MAX_FORCED_VALUE_DIGITS` digits (2,000; read from the IR's equalities, nothing evaluated: `policies.forced_value_digits`; repair round 4) | INVALID_FORMALIZATION | E307 | no |
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
| ENTAILED, INCONSISTENT_PREMISES, UNSATISFIABLE | `premises_relied_on` (always), and `unsat_core.premise_ids` when `produce_unsat_core` is true |

Cores are not guaranteed minimal. The engine always computes the core: the dependency lists,
E108 and E112 rest on it. `produce_unsat_core` only decides whether the raw `unsat_core` record
is serialised, so it never changes dependencies, vacuity or release eligibility.

**Non-results** are UNKNOWN, TIMEOUT, UNSUPPORTED, INVALID_FORMALIZATION and INTERNAL_ERROR.
None of them is a success, and `is_definitive()` returns false for each.
- When Z3 answers `unknown`, the engine classifies it by `reason_unknown`. A reason naming a
  timeout, cancellation, resource limit or interruption becomes TIMEOUT (E400). A memory
  limit becomes UNKNOWN (E402). Anything else becomes UNKNOWN (E401).
- `reason_unknown` is kept in the result.
- The classification depends on Z3's reason text, which can change between Z3 versions.

**Diagnostics on definitive statuses.** The status stays the solver's answer about the encoding.
These diagnostics withhold it as a verdict on the claim (the outcome layer displays
INVALID_FORMALIZATION):
- **E108 (vacuous):** ENTAILED where no premise was used (a tautology); CONSISTENT or
  SATISFIABLE over zero premises; a COUNTEREXAMPLE over zero premises;
- **E110 (unasserted figure):** a COUNTEREXAMPLE that only reassigns a figure the problem defines
  (`b <-> (n = 17)`) but never asserts, where a source states the figure: a grounding on the
  figure or the defined atom was verified by a check in this process (the translation layer
  creates that record from the source clauses that assert the figure: section 9);
- **E111 (unencoded reason):** a COUNTEREXAMPLE that falsifies the conclusion only through
  numeric symbols no premise mentions, where a source states one of them (a verified grounding
  on the symbol, created the same way);
- **E112 (circular):** an ENTAILED proof whose relied-on premises, all the writer's own, restate
  the conclusion. A premise is the writer's own when no check in this process established it,
  whatever kind its grounding claims (`authority.assumed_grounding` is `not has_authority`, policy
  2026.10-v5): a `task_setting`, `rubric_rule` or text label with no check behind it restates the
  point with nothing but the claim itself, while a premise a check verified against the task record
  or a supplied text is a transcription. A restatement is read as written and in the engine's normal
  form (`circular_premises`: ordered operands of symmetric operators, flipped and negated
  comparisons, double negation, `x <= a and x >= a` for `x = a`, literal values), so `5 < x`
  restates `x > 5`; beyond that form, a relied-on premise of the writer's own that Z3 finds
  equivalent to the conclusion under every assignment restates it too (`equivalent_premises`:
  `2 * dt = 82` for `dt = 41`, at most four premises within the decision's remaining time), unless
  it is a calculation over stated figures.

Both shapes are checked on every COUNTEREXAMPLE: one that also has the W110 shape is still checked
for E111, and only an E110 skips the E111 check. A no-verdict code takes precedence over the other
shape's advisory, which is then not carried; two advisories are both reported. The probes run inside
the decision's time bound; a probe that decides nothing (skipped because the bound was spent,
undecided, or failed) leaves the COUNTEREXAMPLE standing only when no source-linked evidence bears
on its symbols, which the evidence check decides without the solver; with such evidence it is E110
or E111 saying that the probe did not decide, so a spent bound never lets a counterexample stand
that the probe could have withheld (repair round 1, re-run review INV-4). With
`produce_unsat_core` a vacuous ENTAILED also carries its raw core record, empty:
`{"premise_ids": [], "includes_negated_conclusion": true}`.

Without that source-linked evidence, the structures of E110 and E111 are the advisory **W110**
and **W111**: a definition is not an assertion and a question may leave a variable unconstrained,
so the COUNTEREXAMPLE stands as the verdict on the encoding, with the coverage warning beside it.
The translation layer counts a source clause as asserting a figure only when no question,
instruction, condition (including a conditional "when" and a symbolic implication such as
`n = 17 ⇒ b`), supposition or hypothesis, claim put forward to be tested, example, definition
(including a symbolic biconditional such as `b ⟺ n = 17`), possibility, obligation, hedge,
attribution (reported speech), negation, quantification or disjunction governs it, and the reader
POSITIVELY recognises the clause as the writer's own statement (a construction it does not
recognise asserts nothing, so the advisory warning and the counterexample stand); what it states
must establish the comparison the encoding defines ("more than 17" is no `n = 17`), and it must
be about the encoding's symbols (not a count of something else). Every source is read for both
shapes: the claim, its supporting claims, the supplied texts and the task record (a figure of a
supplied text or of the task counts for a free conclusion symbol only in a clause about that
symbol). A sentence ends at a full stop before a lower-case symbol that opens a statement, as
before a capital ("Define b. n = 17."), and a question opened by a clause that presents a fact
("Given x = 5 and y = 9, is x < y?") does not govern that clause; see section 9.

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
- `unverified_dependencies` lists premises whose grounding is asserted but was never checked,
  whatever the kind: an unchecked `arithmetic_fact`, `task_setting` or `rubric_rule` is listed
  (until engine 0.4.0 these three were listed nowhere).

**Formal entailment is not permission to release.** `engine.release.release_check(result,
problem, signing_key=..., required_limits=...)` (HTTP: `POST /v1/results/release-check`) is the
engine's part of that decision. A result is eligible only when it is authentic (its signature
verifies), bound (to the problem, internally consistent), current (this engine's versions and
identity, and the validation limits the receiver requires), a positive verdict (ENTAILED,
CONSISTENT or SATISFIABLE for the query), a verdict on the claim (no E108, E110, E111 or E112),
with its evidence computed, and resting on established premises only (no ungrounded or
unverified dependency). Two more conditions come from contract 0.4 (section 10):
- **Rule 8:** no named defect at warning or error by effective severity. A capped diagnostic
  still blocks.
- **Rule 9:** the result was diagnosed by this build's rules, so `argument_rules` equals
  `argdiag-2`. A result verified with `diagnose=False` is refused, and so is one whose diagnosis
  did not finish or ran under other rules (`argdiag-1` included).

Every reason it fails is listed.

## 6. Provenance and integrity

Each result is bound to exactly what produced it:
- **`binding`:**
  - `problem_digest`: SHA-256 of the canonical problem;
  - `config_digest`;
  - `versions_digest` (it covers the identity below);
  - `limits_digest`: SHA-256 of the effective validation limits when they are not the default
    ones (absent for the default limits, which are part of the policy identity);
  - `binding_digest`: SHA-256 of `problem|config|versions`, with `|limits` appended when
    `limits_digest` is present;
  - `smt2`: the SMT-LIB 2 text, for audit.
- **`versions`:** `ir_version`, `engine_version`, `policy_version`, `z3_version`, and the
  immutable identity:
  - `build_id`: digest of the engine, IR and version source, and of the shared
    argument-diagnosis modules `named.py` and `lexis.py`;
  - `schema_id`: digest of the problem, limits, configuration and result JSON Schemas;
  - `policy_id`: digest of the decision policy as data. It binds the argument rules version
    and the digest of the named-code table.
- **`solver_config`:** the configuration the solver ran with.
- **`limits`:** the non-default validation limits the problem was validated under.

Changing the problem, the configuration, any version, the engine source or policy, or the
validation limits changes the binding. A named policy is therefore bound into the result: its
non-default limits are recorded and their digest is part of the binding digest, the nonlinear
`rlimit` cap is part of the configuration digest, and `engine.policies.named_policy_of(result.limits)`
names the policy back (`None` is `linear`). The same problem decided under the same named policy and
configuration binds identically in process and over HTTP. A caller replaying a problem the pipeline
decided names the policy its pipeline result's `limits` record stands for, resets any
`verified: true` the pipeline set (the service refuses it, E505) and leaves the server-controlled
options (`memory_max_mb`, `model_completion`) out of the configuration it sends (the service refuses
them, E100, and its values are the pipeline's), so the HTTP result has the same decision and lists
those premises as unverified dependencies.

**Staleness.** A result is current-policy evidence only for the build that produced it and for a
receiver that requires the limits it was decided under (`engine.provenance.stale_reasons`;
`integrity.handoff.check_result_binding(..., limits=...)`, finding INT-STALE-005). A result of an
earlier release stays inspectable: it parses and its signature still verifies. It is never
displayed as a verdict (the outcome composer shows INTERNAL_ERROR) and never release-eligible
until the problem is verified again.

**Signing.** With a key, the result carries an HMAC-SHA256 `signature` over the canonical
result and a `signature_key_id`. Tampering with any field makes `verify_signature` fail. The
signature covers `signature_key_id` (only `signature` itself is left out of the signed text), so a
result relabelled to another key id fails `verify_signature`. A result of an earlier build, signed
without its key id, still verifies as a historical record; that form is never accepted for a result
of the current build. That earlier form attests who holds the key, never the key id the result names
(repair round 3, INV-6): `engine.provenance.signature_form` reports `bound` or `legacy` (or `None`
for no valid signature), `verify_signature(result, key, key_id=...)` accepts only the bound form for
a receiver that trusts by key id, `release_check` with a `key_id` adds the reason "key id not
attested: ..." for a legacy-form result (which is stale anyway), and `POST
/v1/results/verify-signature` answers `{"valid": true, "key_id_attested": false, "reason": ...}` for
such a record (a current result still answers `{"valid": true}`). `verify_signature` never raises: a signature that is not 64 lower-case hex
digits is refused (HTTP: `valid: false`, `eligible: false`). A result dumped with `exclude_none`
reads an absent `solver_config.memory_max_mb` back as `None`, so it keeps its binding and its
signature; a dump that also leaves out a configuration field that is never `None` (an
`exclude_defaults` or `exclude_unset` dump) reads it back as its default, 512, so every single dump
mode of a genuine result verifies (repair round 1, re-run review security-5 variant). A dump that
excludes both `None` values and defaults cannot be told apart from a default configuration's and is
no round trip.

## 7. Resource bounds

| Setting | Default and range | Notes |
| --- | --- | --- |
| `timeout_ms` | 2,000 ms; 1–120,000 | Applies to each solver call, so entailment may take up to twice the timeout. The E110/E111 coverage checks run inside the same bound (they share the decision's deadline; each gets what is left, at most `timeout_ms` per call; one with nothing left is skipped and decides nothing) and are timed in `timings` (`coverage_probe_figure`, `coverage_probe_reason`). The argument diagnosis has its own bound (section 10). |
| `rlimit` | none | Optional Z3 resource limit, for deterministic cut-offs. |
| `memory_max_mb` | 512; at least 128 | Z3's memory limit is process-wide. The engine therefore scales it with the number of verifications running at once and never lowers it while any run. |
| `random_seed` | 0 | |

Each verification uses a fresh Z3 context.

## 8. Examples, produced by running the baseline

The inputs are the cases in `tests/engine/test_procedures_verify.py`. They were run again
through the CLI on 2026-10-17 with z3-solver 5.1.0.0 (engine 0.5.0), and again on 2026-10-24 for the
rules version of close round 3 (`argdiag-2`; nothing else in them changed). Volatile fields are elided.

### Success: transitivity is entailed (`test_entailment_transitivity`)

Input:

```json
{"ir_version": "1.0", "problem_id": "p1", "request_id": "req1", "claim_id": "c1", "query": "entailment",
 "symbols": [{"name": "x", "sort": "Int"}, {"name": "y", "sort": "Int"}, {"name": "z", "sort": "Int"}],
 "premises": [{"id": "P1", "expr": {"op": "gt", "left": {"op": "var", "name": "x"}, "right": {"op": "var", "name": "y"}}},
              {"id": "P2", "expr": {"op": "gt", "left": {"op": "var", "name": "y"}, "right": {"op": "var", "name": "z"}}}],
 "conclusion": {"id": "C", "expr": {"op": "gt", "left": {"op": "var", "name": "x"}, "right": {"op": "var", "name": "z"}}}}
```

Output (abridged; the identity digests change with every build and are elided):

```json
{"query": "entailment", "status": "ENTAILED",
 "unsat_core": {"premise_ids": ["P1", "P2"], "includes_negated_conclusion": true},
 "premises_relied_on": ["P1", "P2"],
 "ungrounded_dependencies": ["P1", "P2"], "unverified_dependencies": [],
 "counterexample": null, "diagnostics": [], "argument_rules": "argdiag-2",
 "named_diagnostics": [{"code": "ARG-FACT-001", "defect": "lack_of_evidence", "severity": "info", "layer": "engine",
   "claim_ids": ["c1"], "assertion_ids": ["P1", "P2"], "derivation": "engine_recheck",
   "derived_problem_digests": ["…", "…", "…"], "rule_version": "argdiag-2",
   "message": "the proof also needs fact premise(s) that no check established: P1; P2 (P1, P2 relate quantities: a figure relation states no step from a reason to the point, so it gives no missing link); the evidence rules grade them"}],
 "versions": {"ir_version": "1.0", "engine_version": "0.5.0", "policy_version": "2026.10-v5", "z3_version": "5.1.0",
              "build_id": "…", "schema_id": "…", "policy_id": "…"}}
```

`ungrounded_dependencies` lists both premises because they carry no grounding metadata. The
argument diagnosis ran (`argument_rules`) and recorded one info diagnostic: the proof needs
both premises and no check established them, so they are listed for the evidence rules
(ARG-FACT-001). Each is a figure relation (a comparison of two quantities, no implication),
so neither is named a missing link (repair round 5, INV-LINK-1). An info record never blocks
or permits anything by itself. `argument_rules` with no `named_diagnostics` would mean that
the diagnosis ran and named nothing. The entailment holds for the encoding only, and
`release_check` refuses it:
`{"eligible": false, "reasons": ["unresolved dependencies (ungrounded): P1, P2"]}` (signed with
a key and checked under it).

### Failure: a nonlinear product is UNSUPPORTED (`test_invalid_and_unsupported_payloads_become_results_not_exceptions`)

Input: a `consistency` problem over Int `x` and `y`, with a premise
`{"op": "gt", "left": {"op": "mul", "args": [x, y]}, "right": {"op": "int", "value": "0"}}`.

Output (abridged):

```json
{"query": "consistency", "status": "UNSUPPORTED",
 "diagnostics": [{"code": "E201", "message": "'mul' has 2 non-constant factors; only linear arithmetic is supported", "path": "premises[0].expr.left"}],
 "binding": {"smt2": null}, "unsat_core": null, "counterexample": null}
```

No solver call was made, so the result carries no `argument_rules`: the diagnosis was not
computed. The same test also shows that a payload `{"op": "exec"}` becomes
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
  by this contract version.** They are still changing in active development. An injected
  verifier that declares a `task` parameter receives the task record of the request the report
  answers (`fn(claim, report, task=...)`); a two-argument verifier is called as before.

### Translation records (contract 0.2, extended in 0.4; `translate/contracts.py`, translator `0.5.1`)

A record this translator did not make (another `translator_version`, or no `claim_text_sha256`) is displayed
INTERNAL_ERROR whatever its status and is never released (`outcome.translation_staleness`). A report's notes are
bounded: at most 10,000 characters per assumption, assessment criterion or unresolved issue, and 1,000,000 for a
report's notes together; an oversized report is REJECTED (INT-REQ-009). A plan, request, report or claim that states
`course_level` as `null` reads it as `"unknown"` (the same meaning), so it reads back from its canonical dump as it was
written. Provider output over 64 KiB (`parsing.MAX_PROVIDER_TEXT_BYTES`) is refused before it is parsed, and the
translation is TRANSLATION_FAILED with no retry ("provider output too large"). A report or synthesis the channel
receives as a mapping is validated strictly, as the JSON it is: `"yes"` is no boolean and `"1"` no integer, and a
mapping with a coerced value is REJECTED with INT-REQ-009 naming the field.

Every field below is defaulted, so a translation record from before 0.2 still parses; such a
record carries none of them and must be translated and verified again, not trusted.

- **`TaskRecord`** (`task_id`, `request_id`, `text`, `text_sha256`, `issued_by`): the task as the
  router issued it, an application-created, immutable record (`TaskRecord.of(...)` computes the
  digest; a mismatch is refused). With the supplied texts it is the only source of task
  authority, and it is the original task a fidelity reviewer is shown
  (`Translator.translate(..., task=...)`, `verify_claim(..., task=...)`).
- **Task authority** (`GroundingCheck.method == "numeric_in_task"` or `"relation_in_source"`): a
  premise of kind `arithmetic_fact`, `task_setting` or `rubric_rule` is validated (`verified=True`),
  refuted (`verified=False`: the task record was given and states no such figure, or a record
  states a conflicting figure of the same unit; the engine lists it as an ungrounded dependency)
  or unvalidated (`verified=None`; the engine lists it as an unverified dependency). The kind
  itself confers nothing, and a check validates only the premise's WHOLE numeric content: an
  assignment (each symbol compared with a literal, `distance = 120`) when the records state each
  figure so that it establishes that comparison (`numeric_in_task`); any other numeric content, a
  relation that combines symbols (`speed = distance / 8`), only when a record states that same
  formula as a given (`relation_in_source`, read by a closed formula reader: nothing is
  evaluated), or, for a rule of literals, when a record states it in words as a conditional, a
  universal rule or a biconditional (`translate/stated_rules.py`). The figures of a relation
  occurring in a record are no evidence for the relation: an unstated relation stays an unverified
  dependency whatever its grounding label (also when a located excerpt supports the premise's
  quotation), and the release assessment lists it. A figureless task premise is refuted when no task
  record holds its words (read from its label or its meanings), and validated
  (`GroundingCheck.method == "content_in_task"`, repair round 2) when one asserted sentence or clause
  of the task record states each of its literals with its polarity, by their meanings or by the
  premise's label, or when the label writes that sentence's notation in words; a question, a hedged
  or suspended sentence and a condition state nothing.
- **Content of an excerpt** (`GroundingCheck.method == "content_in_excerpt"`, contract 0.4, repair
  round 1): a located excerpt that states a conjunction of the premise's literals verifies it
  (`verified=True`); a located excerpt that states neither the premise's literal nor its point (the
  point dressed as a quotation, a placeholder) refuses it (`verified=False`), so the premise is the
  writer's own for every authority rule. An excerpt about another named subject or another quantity
  does not ground a figure (`figures_in_excerpt`, `verified=False`).
- **Figures the answer derived** (`check_problem_grounding(..., answer_texts=...)`, passed by the
  pipeline: the claim's text, its supporting claims' texts and, since repair round 2, the report's
  original response): a figure the answer's own written
  calculation derived from stated figures grounds where an excerpt is demanded; the divisor of a
  mean of stated addends is no figure the excerpts must state.
- **`GroundingSupport`** (`TranslationResult.grounding_support`): per target, the references
  located, refuted and unchecked, and the support level `complete`, `partial`, `failed` or
  `uncheckable`. Only complete support verifies a grounding; every reference keeps its own check
  (`GroundingCheck.ref_index`), so an unknown second document is surfaced, never hidden.
- **`FigureReading`** (`TranslationResult.figure_readings`): each figure the encoding compares,
  tied to the source span that states it, with its exactness read from the wording (`exact`,
  `rounded`, `unstated`, `given`, `conflicting`, `unsourced`), how it was encoded (`encoded_as`:
  `exact_equality`, `interval` or `other`), the value a written calculation gives (`calculated`) and whether the rounded reading
  rests only on the convention of written calculation (`by_convention`). A figure is the result of a written calculation
  only when the calculation ends at its '=' and the figure ends the expression ("If x = 1/3 then x = 0.33" states no
  calculation for 0.33: the sign equates it with the variable x), and an approximation word or sign is a cue only for the
  figure it is written against. The solver never decides
  that a figure was rounded: an exact or given figure widened into an interval is rejected
  (`exactness`), a rounded figure must use exactly its stated tolerance (`stated precision`), and
  an unstated decimal whose two readings give different verdicts is AMBIGUOUS_TRANSLATION.
- **`RepairRecord`** (`TranslationResult.repairs`): an accepted retry, `syntax` or `semantic`, with
  every change listed. After a semantic rejection the new conclusion is compared with the earlier
  one read as its source states it; a weaker or incomparable conclusion makes the translation
  AMBIGUOUS_TRANSLATION (flag `retry_changed_claim`), so a retry cannot inherit the claim's
  approval. After a rejection for an unasserted figure (E110, the only rejection that asks for a
  premise) every premise the retry adds is checked: it must follow from the rejected attempt's
  premises with the source-asserted atoms asserted, or be established by a grounding check; any
  other added premise makes the translation AMBIGUOUS_TRANSLATION (flag `retry_added_premise`) and
  the release assessment lists "a retry added premises no source asserts". `supported_by_source`
  is true only when every change is what the source states (a figure read at its stated precision,
  or the figure or atom the source asserts).
- **`CoverageNote`** (`TranslationResult.coverage`): for the E110 and E111 shapes, whether a source
  asserts what the encoding leaves open (`source_asserted`, with `evidence`, `source_refs` and
  `evidence_symbols`), bound to the problem's formulas (`problem_digest`). A source asserts a figure
  only in a clause that states it as a fact (one the reader positively recognises as the writer's
  own statement; anything it does not recognise asserts nothing), establishing the comparison the
  encoding defines, about the encoding's symbols (`translate.assertion`); the `detail` of a note
  that finds no assertion names each mention passed over and the construction that decided it
  (`unrecognised` with the word or sign it did not recognise). The pipeline hands this
  decision to the engine as a verified grounding on exactly the symbols involved, so the engine's
  E110/E111 (no verdict) or W110/W111 (advisory) is the same decision; a payload cannot carry
  that record (E505).
- **`ReviewRequest` / `SemanticFidelityReview`**: the review request carries the claim, the
  supporting claims, the task record, the supplied texts (a very long text in part, named in
  `evidence_truncated`), every input's identity and digest (`SourceIdentity`), the
  premise-to-source mapping with its checks (`PremiseSource`) and the figure readings. The review
  is bound to those inputs (`ReviewBinding`); `review.review_currency` says `current`, `stale`
  (a supporting claim, supplied text, task or problem changed, even with the claim text
  unchanged), `unbound` or `without_evidence`. A review never changes the display status.
- **`ReleaseAssessment`** (`ClaimVerificationOutcome.release`, `outcome.assess_release`; policy
  `release-v2` since contract 0.4, `release-v1` before): formal status and permission to release
  are separate. Release needs all of these:
  - the passing status for the query;
  - the engine's release check of the signed result under the composer's key (section 5);
  - every relied-on premise established;
  - no failed grounding check, no partial reference support and no unvalidated task authority;
  - no retry that changed the claim;
  - no structural error;
  - no named defect on the claim at warning or error by effective severity (section 10);
  - a diagnosis that finished: any `diagnosis_incomplete` entry is unresolved ("argument diagnosis
    incomplete (not computed is never read as none found): ..."), as rule 9 is for the engine;
  - a `faithful` review that is current and was made with the evidence.

  Every unresolved item is listed; nothing in the channel or hub releases an answer by itself.

## 10. Named diagnostics (argument diagnosis, rules `argdiag-2`; contract 0.4)

A named diagnostic uses a closed vocabulary to say what is wrong with how an answer argues,
cites or calculates. It says only what deterministic code can tell from the engine result, the
IR, the grounding records and closed reference data. Like every result, it concerns the encoding
and this code only. It never says that a premise is true, that a translation is faithful or that
an interpretation is right.

- **The record** (`epinoic_logic.named.NamedDiagnostic`; the module imports neither z3 nor the
  engine). Empty optional fields are left out of a dump.
  - `code`: a key of `named.NAMED_CODES`, or an existing finding code given a label.
  - `defect`: one of the 28 canonical labels in `named.DEFECT_LABELS`. The key name is fixed.
  - `severity`: never above the code's maximum.
  - `capped_from` and `cap_reason`: the cap reason is `ambiguous_translation` or
    `not_source_bound`.
  - `layer`: `engine`, `claim`, `report`, `stem` or `channel`.
  - `claim_ids` and `assertion_ids`.
  - `missing_link`: `premise_ids`, `antecedent`, `consequent`, `text`, and `expr`. `expr` is an
    IR expression, validated against the IR schema and never evaluated.
  - `evidence`: at most 8 spans.
  - `derivation`: from a closed list.
  - `derived_problem_digests`: at most 24.
  - `related_result_ids`, `rule_version`, and `message` (at most 600 characters).
- **Where it appears:**
  - `VerificationResult.named_diagnostics` holds the engine layer and is set only when non-empty.
  - `VerificationResult.argument_rules` is set whenever the diagnosis ran: `argdiag-2`, or
    `argdiag-2/incomplete:<reason>` when it did not finish (`argdiag-1` before close round 3).
  - The signature covers both fields. Both are left out of every dump while `None`, so a result
    of an earlier release still re-serialises byte-identically.
  - An absent `argument_rules` means "not computed", never "none found".
  - The translation record gains `premise_roles` and `asserted_verified`. A premise role records
    the role, the authority, the marking and the connective.
  - The claim outcome gains `named_diagnostics` and `diagnosis_incomplete`. The outcome's
    diagnostics are the trusted engine result's merged with the claim layer's.
  - `StructuralFinding`, `IntegrityFinding` and the branch `FormalCheck` gain `defect`.
  - The receipt gains `named_diagnostics`: every outcome's, the report-level ones, and one for
    each labelled finding.
- **Severity and caps:**
  - A cap is applied where a diagnostic is made and is recorded in `capped_from`, so each
    diagnostic has one severity everywhere.
  - An ambiguous translation caps every ARG-* and EVD-* code at info, except the equivocation
    codes. The translator passes `severity_cap=("info", "ambiguous_translation")`, which is
    applied before signing.
  - A code whose warning needs a source-bound task is capped at info outside one.
  - Release reads the effective severity: the higher of `severity` and `capped_from`. A cap
    therefore changes what is shown, never what is permitted.
- **Receipt findings:**
  - Each warning or error diagnostic on a material claim becomes one `INT-ARG-001` finding that
    carries its `defect`. This covers diagnostics of an outcome and of the report level.
  - No `INT-ARG-001` is added for a condition that another finding already states:
    ARG-CONTRA-001 is stated by INT-REQ-007.
  - Info diagnostics never reach `findings`, so they never change the receipt status.
  - When the receipt is built, existing codes are labelled through `named.DEFECT_OF_CODE`.
    INT-SUBJ-001 and INT-SUBJ-004 take the FormalCheck's own `defect` first.
- **Display:**
  - Every line of the summary is one line (`named.one_line`), and the model text a summary line or a
    diagnostic message shows has its forgery words written "[...]" (`named.model_text`,
    `named.FORGERY_WORDS`); evidence spans keep the text as written.
  - The outcome summary has a section headed "Argument diagnosis (advisory; the status above is
    unchanged; rules argdiag-2)", directly after the verification lines.
  - The section has at most six lines. Otherwise it reads "none found", "incomplete" or "not
    computed".
  - The scope statement stays last.
  - A diagnostic never changes a display status.
- **Release:**
  - `release_check` applies rules 8 and 9 (section 5).
  - The outcome's release assessment is policy `release-v2` and lists "named defect on this
    claim: <codes>" and "argument diagnosis incomplete ..." for a rule that did not finish; the
    engine release check's own "named defect" reason is kept when the claim's list names no
    blocking diagnostic.
  - The dependency rule already refuses a load-bearing premise that is the writer's own or that
    no check supports.
  - The diagnosis can only make a result less releasable, never more.
- **Which runs are diagnosed:**
  - The claim's own verification is diagnosed: `verify_claim`, `POST /v1/verify` and the CLI.
  - These pass `diagnose=False`, so their results are never release-eligible: the translator's
    internal probes, the integrity cross checks, and the channel's code-built checks (branch
    formal checks and constraint bounds).

**The rules** are implemented; `docs/ARGUMENT_DIAGNOSTICS.md` gives every label with its derivation,
code, example and clean control, and the measured results.
- **Engine layer** (`engine.argument`, `engine/ARGUMENT.md`): ARG-CONTRA-001, ARG-VAC-001 and
  ARG-CIRC-001 from the engine's own status; on an ENTAILED point with no no-verdict code, R0
  decides the point again from the premises a check established and names the writer's links
  (ARG-LINK-001, info, each with its `missing_link`), the unestablished facts and figure relations
  (ARG-FACT-001, info; a figure relation, "x > y", states no step and is never named a leap)
  and the pattern rules over them (ARG-CIRC-002, ARG-CIRC-003, ARG-AC-001, ARG-DA-001, ARG-FD-001,
  ARG-HG-001, ARG-CL-001, ARG-EQ-003); on a COUNTEREXAMPLE, its shape (ARG-REFUTE-001, ARG-AC-001,
  ARG-DA-001, ARG-HG-001, ARG-NS-001, ARG-PART-001, ARG-NS-002, ARG-EQ-002, ARG-INV-001). Derived
  runs are data-built subsets of the bound problem: at most 24 per result, each under
  `min(timeout_ms, 1000)` ms and at most `min(4 × timeout_ms, 8000)` ms in all.
- **Claim and report layers** (`translate.diag_argument`, `translate.diag_evidence`): ARG-EQ-001,
  the claim form of ARG-CIRC-001, ARG-NS-003 (repair round 3: an unbridged leap between two named
  things joined only by a connective; repair round 4: a sentence that only names the two things does
  not bridge it) and ARG-BARE-001; EVD-SRC-001, EVD-SRC-003, EVD-SRC-004,
  EVD-SRC-005 (repair round 1: a task-authority premise with no excerpt that the task material does
  not hold, a warning in every task), EVD-LACK-001, EVD-FIG-001, EVD-AUTH-001 and EVD-CHERRY-001;
  the report rules EVD-SRC-002 and EVD-LACK-002, info only ("not checked", never "false").
- **STEM layer** (`stem.reference`, the STEM checks): ST-REF-001, ST-REF-002, ST-RANGE-001,
  ST-WORK-001, ST-GIVEN-002, ST-GIVEN-003, ST-GIVEN-004, ST-SCOPE-002, ST-STEP-002 and ST-STEP-003
  (repair round 3: a rewrite inside a chain whose sides differ at a sample point) are findings; ST-UNIT-003, ST-STEP-001 and
  ST-ROUND-001 are engine-decided checks whose failure (INT-SUBJ-001, or INT-SUBJ-004 for a reading
  the report did not state) carries the defect.
- **Channel**: INT-ARG-001 (above); INT-REQ-017, an answer built on a peer report that hands a
  system check result to the reader as subject content; INT-XENC-001, two encodings of one claim
  that reach opposite definitive answers (neither verdict is withdrawn).
- **Pack findings that name a label** (`named.DEFECT_OF_CODE`): besides the codes of
  `docs/ARGUMENT_DIAGNOSTICS.md`, section 3.3, CORE-SRC-007 (repair round 4, warning): a figure the
  answer credits to a named data table for a year that the table states otherwise; its message says
  "for no year" (`invented_figure`) or names the other year (`source_mismatch`).

The response gate (`channel.gate.assess_response`) counts a claim with a named diagnostic at warning
or error by effective severity as unresolved, never as passed, and an INT-ARG-001 finding as
unresolved, never as failed. A positive display passes only when the engine's diagnosis ran to the end
on its result (`argument_rules` is the rule version), no rule of the outcome is listed in
`diagnosis_incomplete`, and a release assessment was made and permits release (repair round 3,
INV-7); a finding carried from an earlier receipt (INT-HIST-001) is recognised only by making it again
from the receipt's structured history with the channel's own constructor
(`channel.contracts.carried_finding`), never by reading its message (ADV3-02). Every status and dependency list stays exactly what it was: the
diagnosis only adds records and findings, and can only make a result less releasable.

## 11. PROPOSED (not implemented)

- Non-zero CLI exit codes for non-definitive statuses. Today the exit code is always 0.
- A published JSON Schema for `Problem` and `VerificationResult`, generated from the models.
- `translator_version` in `VerificationResult.versions`. Today it is reported in translation
  records, by `epinoic-logic version` and in the service's version response, but not in an
  engine result.
- A dependency lock. `pyproject.toml` gives lower bounds only: `z3-solver>=4.13`,
  `pydantic>=2.6`.
- A frozen, versioned list of report-level finding codes for the receiving side.

## 12. Changes to this contract

- A change to the IR schema bumps `IR_VERSION`.
- A change to compilation or procedures bumps `ENGINE_VERSION`.
- A change to limits or the allowlist bumps `POLICY_VERSION`.
- Each of these also bumps this contract's minor version and updates the examples.
- Field removals, or changes to status meanings, need agreement from the receiving owner before
  they merge.
- Independently of these rules, the bound identity (`build_id`, `schema_id`, `policy_id`) changes
  with any change to the engine or IR source, the schemas or the decision policy, so a missed
  version bump cannot make another build's result current.

**0.3 to 0.4** (engine 0.5.0, policy 2026.10-v5, translator 0.5.0, rules argdiag-1; IR 1.0
unchanged; section 10):
- `VerificationResult` gains `named_diagnostics` and `argument_rules`. Both are signed and
  absent while `None`.
- `verify` gains `diagnose=True` and `severity_cap=None`.
- The outcome gains `named_diagnostics` and `diagnosis_incomplete`.
- The translation record gains `premise_roles` and `asserted_verified`.
- Structural, integrity and formal-check findings gain `defect`.
- The receipt gains `named_diagnostics` and the `INT-ARG-001` finding.
- `release_check` gains rule 8 (no named defect by effective severity) and rule 9 (diagnosed by
  these rules). The release assessment is `release-v2`.
- The build identity covers `named.py` and `lexis.py`. The policy identity binds the argument
  rules version and the named-code table.
- A result of engine 0.4.0 still parses and its signature still verifies. It is stale, and it
  is not release-eligible until the problem is verified again.
- The rules of section 10 are implemented (engine, claim, report, STEM and channel layers).
- Only a check in this process confers authority, for circularity too (E112, section 4); a
  restatement is also read in the engine's normal form.
- The same release carries the re-run review fixes, with no further version change (the build
  identity already separates this build's results): the signature covers `signature_key_id` and
  `verify_signature` never raises (section 6); both coverage shapes are checked on every
  COUNTEREXAMPLE, inside the decision's time bound (sections 4 and 7); a vacuous ENTAILED carries
  its empty core record; the CLI takes its signing key from a file or an environment variable and
  refuses one under 16 bytes (section 2); a translation record of another translator, report notes
  over their bounds, a `null` `course_level`, provider output over 64 KiB and a coerced value in a
  mapping are handled as section 9 states.
- Repair round 1 of the argument diagnosis, with no further version change (rules `argdiag-1`,
  release `release-v2`): `GroundingCheck.method` gains `content_in_excerpt`; the named-code table
  gains EVD-SRC-005, ST-REF-002 and ST-GIVEN-003; `check_problem_grounding` gains `answer_texts`;
  the release assessment reads `diagnosis_incomplete`; summaries and display lines are one line and
  mask model text; a coverage probe (E110, E111) that decided nothing withholds the verdict when
  source-linked evidence bears on its symbols (section 4); a result of every single dump mode
  verifies (section 6). The channel: an AMBIGUOUS_TRANSLATION or UNSUPPORTED claim leaves no clean
  receipt; a report's copy of a request text must match its metadata too (INT-REQ-002); a router
  forward that names no delivery is INT-HANDOFF-018 (warning); an answer delivered as a one-key answer
  object is read as its text, an answer that is one string in double quotes stays a quotation (checked
  as one), and a JSON report followed by more text is refused (INT-REQ-009).

- Repair round 2 of the argument diagnosis, with no further version change (rules `argdiag-1`,
  release `release-v2`): the engine refuses exact arithmetic beyond `MAX_COEFFICIENT_DIGITS` with
  `E307` (INVALID_FORMALIZATION, a limit code for the integrity layer's cross checks too), and the
  policy manifest gains `max_coefficient_digits`; `E112` also reads a restatement Z3 finds
  equivalent beyond the normal form (section 4); the named-code table gains ARG-LINK-002 (info),
  EVD-SRC-006 (warning) and ST-GIVEN-004 (warning; 48 codes); a relayed report is a peer document by
  its id, author or provenance; a mapping report whose original response is one JSON object wrapping
  the answer has an answer; a request with no visible character is REJECTED (INT-REQ-009); a
  contract error of one field names the validator's message, never the value. The translation
  side: `GroundingCheck.method` gains `content_in_task` (above); premises that contradict each other are never refused as circular, so the engine decides
  INCONSISTENT_PREMISES (consistency before entailment); a provider output refused for its form or
  policy that asserted `verified=true` keeps the E505 line among the translation's diagnostics
  beside its refusal; a figureless task premise whose label writes a task sentence's notation in
  words is validated by that sentence (`content_in_task`).

- Repair round 3 of the argument diagnosis, with no further version change (rules `argdiag-1`,
  release `release-v2`, policy 2026.10-v5): the named-code table gains ARG-NS-003 (warning, claim)
  and ST-STEP-003 (warning; 50 codes); `engine.provenance` gains `signature_form`, and
  `verify_signature` gains `key_id` (section 6); the verify-signature route answers
  `key_id_attested: false` for a legacy-form record, and the release check names its key id as not
  attested; a claim that states its own reason ("A, so B") is eligible with no supporting claim
  (`translate.eligibility`, policy 2026.10-v5); a figureless task-authority premise with no excerpt
  is refuted again when a task sentence uses its words without stating it, when the task only
  reports it as a view or asks it, and when it is an "if", "iff" or "or" no record states (as before
  repair round 2); a peer document id is compared after normalisation (NFKC, whitespace and format
  characters dropped, case folded: `translate.grounding.is_peer_id`), in the channel too; the
  response gate reads `argument_rules`, `diagnosis_incomplete` and the release (section 10).

- Repair round 4 of the argument diagnosis, with no further version change (rules `argdiag-1`,
  release `release-v2`, policy 2026.10-v5; the named-code table is unchanged, 50 codes): under a
  policy that allows nonlinear terms the engine refuses a problem whose products force values beyond
  `MAX_FORCED_VALUE_DIGITS` (2,000 digits) with `E307` before it compiles, and the policy manifest
  gains `max_forced_value_digits` (so the policy identity changes with it); `E112` also reads a
  restatement split across premises of the writer's own, tested together; ARG-VAC-001 is an info
  record on a proof over no premise at all; the release assessment and the engine's release rule 8
  list capped diagnostics under their own line, with their cap and no defect label, still blocking;
  `named.DEFECT_OF_CODE` maps CORE-SRC-007 (above). The translation side: an "or" the task states
  validates a task-authority disjunction (`GroundingCheck.method` `relation_in_source`), a task
  sentence in other words validates a task fact (`content_in_task`), a conversion the task gives and
  the count, total or mean of a stated list ground their figures, and a premise cited only to a
  peer's report is unvalidated; a relayed report is a peer document when its author or provenance
  holds an agent word (specialist, agent, combinator) after normalisation. Quotation roles: the
  correction and suggestion roles are read only in a marking, feedback, correction or editing task,
  which the channel sets from the plan (`adapters.markdown.quotation_task`); every other quoted span
  of an analysis is checked as a quotation.

- Repair round 5 of the argument diagnosis, with no further version change (rules `argdiag-1`,
  release `release-v2`, policy 2026.10-v5; the named-code table keeps its 50 codes, and ARG-CIRC-003
  is also made in the report layer: `named.NAMED_CODES["ARG-CIRC-003"].layers` is `("engine",
  "report")`): a figure relation the proof needs is listed under ARG-FACT-001, never named a
  writer's link (ARG-LINK-001), so the section 8 example records ARG-FACT-001 at info; the task type
  a report or a claim states about itself is advisory for the quotation roles and never widens them
  (`quotation_task(..., advisory=True)` in the claim and report diagnoses and the branch packs);
  `epinoic-logic check-report` gains `--task-type`, the task type the operator states for the
  report's quotation roles (an envelope's own `task_type`, the request's metadata, is read as
  before; a `SpecialistReport` document's own `task_type` never widens the roles). The translation
  side: an excerpt whose clause contradicts the literal it is cited for refutes it
  (`GroundingCheck.method` `content_in_excerpt`, `verified=False`); a definition or a closed
  enumeration a record states is a rule it states; a unit glossed in parentheses is the symbol's
  declared unit; a relayed agent's text is a peer document under the labels "relay:", "rep-", an AI
  author or the router. The text intake unwraps envelopes nested up to four levels and one envelope
  tag, and refuses a structured reply cut off in transit (INT-REQ-009).

- Close round 1 of the argument diagnosis, with no further version change (rules `argdiag-1`,
  release `release-v2`, policy 2026.10-v5; the named-code table is unchanged): a source rule a
  record states only hedged, framed, restricted or with a part of its condition dropped is refuted
  as the premise that encodes it plainly (`GroundingCheck.method` `relation_in_source`,
  `verified=False`); a task sentence of another time, tense or direction of change refutes the
  premise it seems to state (`content_in_task`, `verified=False`); ARG-CIRC-001 is an info record
  for a claim that only restates the task under the task's authority and gives no reason (the
  refusal stands); no field, status or code changes.

- Close round 2 of the argument diagnosis, with no further version change (rules `argdiag-1`,
  release `release-v2`, policy 2026.10-v5; the named-code table is unchanged): a figureless task
  premise that shares an atom with the point is never validated by a task sentence
  (`content_in_task` is not recorded for it; the circularity rules, E112, decide it, as before
  repair round 4); the open precision of a trailing-zero whole number is not read at its last
  digit for a term that takes only whole values (a count compared over `to_real` is decided as
  over Int); a span after "unlike", "rather than" or "instead of" is a `quotation` role again; a
  synthesis receipt carries no INT-HIST-001 for a subject finding about a report's paragraphs or
  sentence style (ES-STR-, ES-STY-, HI-STR-), which stays in its `history`; no field, status or
  code changes.

- Close round 3 of the argument diagnosis moves the translator to `0.5.1` and the rules to
  `argdiag-2` (release `release-v2`, engine 0.5.0, policy 2026.10-v5, contract 0.4; the named-code
  table is unchanged), so a translation record of an earlier round of the release reads as stale and
  a result diagnosed under `argdiag-1` is refused by release rule 9. EVD-SRC-001 no longer names a
  task-authority premise that restates a supposition the task sets ("Assume that ..."); a span right
  after a reporting verb under a negation ('never says "x"', 'not only writes "x"') is a `quotation`
  role again; the synthesis ledger's figure readers and the cross-report consistency check give the
  same answers in linear work (a definitive joint result is cited again for an identical joint
  problem, so `formal_result_id` of a repeated contradiction is the first check's); no field, status
  or code changes.

- Accuracy round 1 of the argument diagnosis (versions unchanged: translator 0.5.1, rules `argdiag-2`,
  engine 0.5.0, policy 2026.10-v5, contract 0.4; the named-code table is unchanged) narrows readings
  that raised false alarms on correct answers and adds three STEM readings: a forward or relay to a
  peer specialist, and a synthesis, carry as INT-HIST-001 only errors, the warnings INT-SUBJ-004,
  INT-ARG-001 and INT-REQ-017 and the subject findings that name a STEM defect (every other warning
  stays in `history`; a forward to the combinator carries everything); a general-knowledge fact of a request that invites own knowledge is an info
  record (`not_source_bound`), not EVD-LACK-001 at warning; a generic rule written with "when" is a
  stated rule; the STEM front end plans a traced `unit` companion for a working that substitutes into
  no symbol, a `giv` check for a bare value in place of the request's quantity, and an `rnd` check for
  a rounding worded "which rounds to" or "to the nearest ..."; no field, status or code changes.

- Accuracy round 2 of the argument diagnosis (versions unchanged, as for round 1) reverts or replaces
  round-1 readings that still raised false alarms: a document's stance is read only where every
  statement it makes about what the claim's stance is about carries a stance word; a label-only
  task-authority premise whose words a sentence the task asserts holds is an info record of
  EVD-SRC-001, not a warning (still unvalidated, so the result stays not releasable); a stated rule
  applied to the case the question names is the source's rule; a cause phrase that only restates the
  point is ARG-CIRC-003; the general branches plan the traced `unit` companion of a working of the
  request's quantities (`core-req-…`); a `giv` check reads only a miscopy, and an `rnd` check is not
  planned against the value before the rounding; no field, status or code changes.

**0.2 to 0.3** (component versions unchanged; the build and policy identities change with the source):
- `POST /v1/verify` and `epinoic-logic verify` take a named engine policy (`linear`, `nonlinear`,
  `joint`; `engine.policies.NAMED_POLICIES`, `named_policy`), applied exactly as the in-process caller
  of that policy applies it, so the eight problems of the end-to-end simulation of 16 October 2026
  that decided differently over HTTP (seven STEM checks under `nonlinear`, one joint check) now decide
  as in the pipeline; an unknown name is refused (HTTP 400 `E100`, CLI exit 2); the release check
  shares the allowlist; `named_policy_of` names the policy of a result's limits record; the policy
  manifest lists the named policies (`named_policies`).

**0.1 to 0.2** (engine 0.4.0, policy 2026.10-v4, translator 0.4.0):
- the unsat core is always computed; `produce_unsat_core` only controls the serialised record;
- an unchecked `arithmetic_fact`, `task_setting` or `rubric_rule` is an unverified dependency, and
  a check validates a premise's whole content (a relation only by a record that states it,
  `GroundingCheck.method == "relation_in_source"`);
- E110 and E111 need source-linked evidence (a source clause that asserts the figure, read from
  its grammar and positively recognised as the writer's own statement); without it the advisory
  W110 and W111 are added and the COUNTEREXAMPLE stands; a
  retry after E110 may add only what the source asserts (flag `retry_added_premise` otherwise);
- `versions` binds `build_id`, `schema_id` and `policy_id`; `binding.limits_digest` binds
  non-default limits; `check_result_binding` takes the receiver's required `limits`;
- `engine.release.release_check` and `POST /v1/results/release-check` state the current-policy
  release check;
- translation side (translator 0.4.0, prompts `translate_v2` and `review_v2`; `translate_v1` and
  `review_v1` stay packaged unchanged): `TaskRecord`, task-authority validation, per-reference
  `GroundingSupport`, typed quantities (`20%` states `0.2` and `1/5` alike; a figure stated as
  rounded, "x is 0.33 to 2 decimal places", states the interval of its tolerance, so its exact
  transcription and the interval at exactly that tolerance both ground), `FigureReading` with
  exactness from the wording, `RepairRecord`, `CoverageNote` handed to the engine as coverage
  evidence, the evidence-carrying and bound review, and `ReleaseAssessment` (section 9).
