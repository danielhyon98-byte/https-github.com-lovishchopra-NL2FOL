# service — authenticated boundary

`create_app(settings)` builds the FastAPI application: `GET /healthz` (versions
only), `POST /v1/verify` (problem + optional solver config + optional engine
`policy` → signed `VerificationResult`), `POST /v1/results/verify-signature`,
`POST /v1/results/release-check` (result + optional problem + optional required
policy `linear`, `nonlinear` or `joint` → `{eligible, reasons, current}`: the
engine's current-policy release check under the service key, so a genuine result of
an earlier release verifies as signed but is never eligible), and `POST /v1/outcomes`
(report + claim id + fixture responses → `ClaimVerificationOutcome`).

**Named engine policies.** A request may name the engine policy its problem is decided
under, `linear` (the default), `nonlinear` or `joint` (`engine.policies.NAMED_POLICIES`),
and never limits of its own. The service applies the name exactly as the in-process caller
of that policy does (`engine.policies.named_policy`): `nonlinear` opens the nonlinear-term
gate and caps `config.rlimit` at `NONLINEAR_RLIMIT` (a lower one is kept), as the channel's
STEM checks run; `joint` raises the shape bounds to `JOINT_LIMITS` (no nonlinear terms), as
the cross-agent joint checks run. The same problem therefore gets the same decision over HTTP
as in the pipeline (before this, 8 of 301 problems of the end-to-end simulation of 16 October
2026 did not: seven STEM checks came back UNSUPPORTED and one joint check INVALID_FORMALIZATION).
The policy is bound into the result's identity: non-default limits are recorded under the
signature with their digest in the binding, the `rlimit` cap is in the configuration digest,
`engine.policies.named_policy_of(result.limits)` names the policy back, and the release check
treats the result as current only for a receiver that names the same policy (one allowlist for
both routes). A backend replaying a problem the pipeline decided names the policy its pipeline
result's `limits` record stands for, and resets any `verified: true` the pipeline set (the
service refuses a client-asserted verification, so the result lists those premises as
unverified dependencies). An unknown name, a case or whitespace variant, null, a number or an
object of limits is 400 `E100` before anything runs; authentication, the rate limit, the
body-size limit (which, not the policy, bounds how large a problem can be sent), the per-call
timeout and the concurrency limit apply under every policy.

`config.produce_unsat_core` is an output option only: the engine computes the core
either way, so the dependency lists, `E108`, `E112` and the release check of a result
are the same whichever value a client sends. A client cannot certify a grounding
(nested `verified: true` is refused, `E505`), so a model-chosen `arithmetic_fact`,
`task_setting` or `rubric_rule` in a submitted problem is listed as an unverified
dependency in the signed result.

Controls: bearer token compared in constant time (401), request body size limit
(413), per-process concurrency semaphore (503), per-token token bucket (429),
rejection of any top-level self-certification field such as `verified` or
`advisory_verification_status` (400), generic error bodies with a request id and
no stack traces, verification run off the event loop. Client-derived identifiers
(`claim_id`, `result_id`, outcome ids) reach the log only when they are plain ids (letters, digits and `._:@#-`, at most
128 characters); any other value is logged as `sha256:<first 16 hex digits>`, so no client input starts a new log
record. The signature routes never fail on a hostile result: a signature that is not 64 lowercase hex characters, or
a result holding a lone UTF-16 surrogate, answers `valid: false` / `eligible: false` (or 400 `E100`), never 500, and
a genuine result re-posted after an `exclude_none` dump (no `memory_max_mb`) still verifies. The signing key and token
come from environment variables; the browser never talks to this service directly.
