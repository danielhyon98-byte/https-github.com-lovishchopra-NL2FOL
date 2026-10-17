# Service test data

`e2e_policy_problems.json`: the eight engine problems of the end-to-end simulation of 16 October 2026 that
`POST /v1/verify` decided differently from the pipeline (8 of 301 genuine-pass problems), because the request could not
name the engine policy the pipeline had used: seven STEM checks the channel ran under the `nonlinear` policy and one
cross-agent joint check run under `joint`. Each entry keeps the problem as the pipeline built it (its groundings'
`verified` flags were set by checks in that process; a caller resets them before posting, since the service refuses a
client-asserted `verified: true`), the solver configuration and limits the pipeline used, its decision
(`pipeline_status`) and what the service returned without a policy (`http_status`). Used by
`tests/service/test_named_policy_over_http.py`.
