# service — authenticated boundary

`create_app(settings)` builds the FastAPI application: `GET /healthz` (versions
only), `POST /v1/verify` (problem + optional solver config → signed
`VerificationResult`), `POST /v1/results/verify-signature`, and `POST /v1/outcomes`
(report + claim id + fixture responses → `ClaimVerificationOutcome`).

Controls: bearer token compared in constant time (401), request body size limit
(413), per-process concurrency semaphore (503), per-token token bucket (429),
rejection of any top-level self-certification field such as `verified` or
`advisory_verification_status` (400), generic error bodies with a request id and
no stack traces, verification run off the event loop. The signing key and token
come from environment variables; the browser never talks to this service directly.
