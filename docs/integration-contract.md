# Integration contract: translator and Z3 engine

- **Contract version:** 0.3 (2026-10-17). Version 0.1 described commit
  `3147d08e0aa63d5eeaceb1072754f29e3862164d` (engine `0.2.0`); 0.2 describes the engine fixes of
  the external review of 12 October 2026; 0.3 adds the named engine policy a caller requests over
  HTTP and on the command line, after the end-to-end simulation of 16 October 2026 (see section 11
  for what changed). The component versions are unchanged by 0.3.
- **Component versions:**
  - IR `1.0`
  - engine `0.4.0`
  - policy `2026.10-v4`
  - translator `0.4.0`

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
- A payload that arrives as JSON text, bytes or a dict cannot certify itself: any
  `verified: true` it contains is discarded, with diagnostic E505.
- Only deterministic checks run in the same process may set `verified`. Only such a record
  confers task or source authority: a `kind` is the proposer's claim, never a validation.

### Entry points (implemented)

| Entry point | How | Notes |
| --- | --- | --- |
| Python | `epinoic_logic.engine.verify(problem_or_raw, config=SolverConfig(), limits=DEFAULT_LIMITS, signing_key=None, key_id=None)` | Never raises. Every failure becomes a result. |
| CLI | `epinoic-logic verify FILE [--timeout-ms N] [--rlimit N] [--policy NAME] [--signing-key-hex HEX --key-id ID]` | Prints the result JSON. **Exits 0 for every status**, including failures; read `status`. `--policy` is `linear` (default), `nonlinear` or `joint`; an unknown name exits 2 with a JSON error. |
| HTTP | `POST /v1/verify`, `POST /v1/results/verify-signature`, `POST /v1/results/release-check`, `POST /v1/outcomes`, `GET /healthz` (`epinoic-logic serve`) | Needs `EPINOIC_SERVICE_TOKEN` and `EPINOIC_SIGNING_KEY` in the environment. Optional limits: `EPINOIC_MAX_BODY_BYTES`, `EPINOIC_MAX_CONCURRENCY`, `EPINOIC_RATE_PER_MINUTE`. The service refuses a client-supplied `memory_max_mb`. `POST /v1/verify` takes `{problem, config?, policy?}`: `policy` names a named policy (above; `linear` by default), anything else is HTTP 400 `E100` before anything runs, and authentication, the rate limit, the body-size limit (which bounds the problem size under every policy) and the concurrency limit apply unchanged; the release check takes the same names as its required policy. Tested in-process and over a local socket in the test suite; never deployed. |

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
  the conclusion.

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
unverified dependency). Every reason it fails is listed.

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
  immutable identity `build_id` (digest of the engine, IR and version source), `schema_id`
  (digest of the problem, limits, configuration and result JSON Schemas) and `policy_id` (digest
  of the decision policy as data).
- **`solver_config`:** the configuration the solver ran with.
- **`limits`:** the non-default validation limits the problem was validated under.

Changing the problem, the configuration, any version, the engine source or policy, or the
validation limits changes the binding. A named policy is therefore bound into the result: its
non-default limits are recorded and their digest is part of the binding digest, the nonlinear
`rlimit` cap is part of the configuration digest, and `engine.policies.named_policy_of(result.limits)`
names the policy back (`None` is `linear`). The same problem decided under the same named policy and
configuration binds identically in process and over HTTP. A caller replaying a problem the pipeline
decided names the policy its pipeline result's `limits` record stands for, and resets any
`verified: true` the pipeline set (the service refuses it, E505), so the HTTP result has the same
decision and lists those premises as unverified dependencies.

**Staleness.** A result is current-policy evidence only for the build that produced it and for a
receiver that requires the limits it was decided under (`engine.provenance.stale_reasons`;
`integrity.handoff.check_result_binding(..., limits=...)`, finding INT-STALE-005). A result of an
earlier release stays inspectable: it parses and its signature still verifies. It is never
displayed as a verdict (the outcome composer shows INTERNAL_ERROR) and never release-eligible
until the problem is verified again.

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

Output (abridged; the identity digests change with every build and are elided):

```json
{"query": "entailment", "status": "ENTAILED",
 "unsat_core": {"premise_ids": ["P1", "P2"], "includes_negated_conclusion": true},
 "premises_relied_on": ["P1", "P2"],
 "ungrounded_dependencies": ["P1", "P2"], "unverified_dependencies": [],
 "counterexample": null, "diagnostics": [],
 "versions": {"ir_version": "1.0", "engine_version": "0.4.0", "policy_version": "2026.10-v4", "z3_version": "5.1.0",
              "build_id": "…", "schema_id": "…", "policy_id": "…"}}
```

`ungrounded_dependencies` lists both premises because they carry no grounding metadata. The
entailment holds for the encoding only, and `release_check` refuses it:
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
  by this contract version.** They are still changing in active development. An injected
  verifier that declares a `task` parameter receives the task record of the request the report
  answers (`fn(claim, report, task=...)`); a two-argument verifier is called as before.

### Translation records (contract 0.2; `translate/contracts.py`, translator `0.4.0`)

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
  evaluated). The figures of a relation occurring in a record are no evidence for the relation:
  an unstated relation stays an unverified dependency whatever its grounding label (also when a
  located excerpt supports the premise's quotation), and the release assessment lists it.
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
- **`ReleaseAssessment`** (`ClaimVerificationOutcome.release`, `outcome.assess_release`, policy
  `release-v1`): formal status and permission to release are separate. Release needs the passing
  status for the query, the engine's release check of the signed result under the composer's key
  (section 5), every relied-on premise established, no failed grounding check, no partial
  reference support, no unvalidated task authority, no retry that changed the claim, no
  structural error, and a `faithful` review that is current and was made with the evidence. Every
  unresolved item is listed; nothing in the channel or hub releases an answer by itself.

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
- Independently of these rules, the bound identity (`build_id`, `schema_id`, `policy_id`) changes
  with any change to the engine or IR source, the schemas or the decision policy, so a missed
  version bump cannot make another build's result current.

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
