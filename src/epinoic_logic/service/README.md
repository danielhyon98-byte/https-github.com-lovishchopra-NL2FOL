# service — authenticated boundary

`create_app(settings)` builds the FastAPI application: `GET /healthz` (versions
only), `POST /v1/verify` (problem + optional solver config → signed
`VerificationResult`), `POST /v1/results/verify-signature`,
`POST /v1/results/release-check` (result + optional problem + optional required
policy `linear`, `nonlinear` or `joint` → `{eligible, reasons, current}`: the
engine's current-policy release check under the service key, so a genuine result of
an earlier release verifies as signed but is never eligible), and `POST /v1/outcomes`
(report + claim id + fixture responses → `ClaimVerificationOutcome`).

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
no stack traces, verification run off the event loop. The signing key and token
come from environment variables; the browser never talks to this service directly.
