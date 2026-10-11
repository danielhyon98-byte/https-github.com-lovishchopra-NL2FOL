# Repository Audit — Epinoic AI Logic Translator and Z3 Verification Engine

Audit date: 2026-10-11. Scope: the two repositories made available to the engineering
session, the uploaded archives, and the context documents. Every statement below is
marked as **verified** (observed directly in this session, with evidence) or
**inference**.

## 1. Governing documents

| Document | Status | Notes |
| --- | --- | --- |
| `specifications/02_Z3_Logic_Verification_Engine_Specification.md` | **MISSING** | Named as the governing specification by the context pack. Not in the uploads, the archives, either repository, or the session filesystem. Nothing here is derived from it. |
| `specifications/03_Overseer_Agent_Specification.md` | **MISSING** | Governs Overseer behaviour; integration with the Overseer is therefore specified only as versioned contracts. |
| `references/ib-agent-training-pack-v2/` | **MISSING** | Subject-profile configuration in `translate/subjects.py` is working configuration, not confirmed against official material. |
| `00_PROJECT_CONTEXT_AND_ARCHITECTURE.md` | provided | Vision, architecture, integrity policy, implementation order (§10). Copied to `docs/context-pack/`. |
| `01_CLAUDE_CODE_START_HERE.md`, `README.md` | provided | Copied to `docs/context-pack/`. |
| Kickoff prompt (`04_Claude_Code_Implementation_Kickoff.md`) | provided | Detailed engine requirements and test list. |
| English specialist knowledge documents (6 files) | provided | Example specialist agent: `master_prompt.txt`, `application.md`, `interpretation.md`, `paragraphs.md`, `formatting.md`, `examples.md`. Used as the first adapter and as QA corpus. Not committed to the repository (user material). |

## 2. What was provided and what it actually is

| Item | Verified finding |
| --- | --- |
| `danielhyon98-byte/https-github.com-Z3Prover-z3` | Empty at audit start (zero commits, zero branches on GitHub). Now holds an unmodified mirror of the uploaded upstream Z3 source (2938 files) plus `EPINOIC_MIRROR_NOTE.md`. |
| `danielhyon98-byte/https-github.com-lovishchopra-NL2FOL` | Empty at audit start. Now holds this proprietary program. No code from upstream `lovishchopra/NL2FOL` (MIT, HEAD 67fd364, 2025-03-14) was copied; see `THIRD_PARTY_NOTICES.md`. |
| `z3-master.zip` (uploaded twice, identical SHA-256 b2119cdc…) | Upstream Z3Prover/z3 source, `scripts/VERSION.txt` = 5.1.0.0, release notes list 5.2.0 in progress. It is the solver, not an application. |
| User's accessible repositories | Only the two above (checked via the repository listing). No Epinoic AI application repository exists in the account. |

## 3. Component inventory against the kickoff list

At audit start every component was **absent**: no frontend, backend, Cloudflare
Workers configuration, authentication, database, document ingestion or retrieval,
model-provider adapters, router, subject specialists, combinator, Overseer, Z3
integration, task queue, logging, or tests. The only "Z3 implementation" available
was the upstream solver source.

What exists now is this repository; see `docs/STATUS.md` for the current
planned / implemented / tested / deployed table.

## 4. Verified runtime facts (evidence in `docs/evidence/`)

| Fact | Evidence |
| --- | --- |
| Z3 5.1.0 Python bindings work on this Linux x64 host: entailment unsat, counterexample model, inconsistent premises unsat, `2x=1` unsat over Int and sat over Real with exact `1/2`, 50 ms timeout returns `unknown` with reason `timeout`, quantified entailment unsat. | `evidence/python_smoke/` |
| Published npm `z3-solver@5.2.0` WASM: 34,938,413 bytes raw, 7,892,649 bytes gzip; built with `-pthread -s USE_PTHREADS=1`; uses `worker_threads` in Node; entailment in ~370 ms including initialisation. | `evidence/node_smoke/`, `evidence/artifact_facts.txt`, upstream `src/api/js/scripts/build-wasm.ts` |
| Local `workerd` (2026-10-06) exposes `SharedArrayBuffer` and shared WASM memory but **no `Worker` constructor**, and `Atomics.wait` throws "cannot be called in this context"; the Z3 module loads as a `WebAssembly.Module` with 116 imports including `env.memory`. | `evidence/workerd_probe/result.json` |
| Cloudflare Workers limits (docs source, `workers/platform/limits.mdx`): Worker size 64 MiB uncompressed, no compressed limit; startup 1 second for global scope; CPU 10 ms (Free) / 5 min (Paid, default 30 s, `limits.cpu_ms`); memory 128 MB per isolate including WebAssembly; no HTTP duration limit. | docs source clone, quoted in session |
| Cloudflare Containers (`containers/platform/limits.mdx`, `pricing.mdx`): custom instance types 1–4 vCPU, up to 12 GiB memory, 20 GB disk; billed per 10 ms with included usage on the $5/month Workers Paid plan; reached from a Worker binding. | docs source clone |
| PyPI publishes `z3_solver-5.1.0.0-py3-none-pyemscripten_2026_0_wasm32.whl` (6.0 MB), built single-threaded as a side module for CPython 3.14 (`pyproject.toml` in upstream). | PyPI JSON index; upstream `src/api/python/pyproject.toml` |
| `developers.cloudflare.com` is blocked by this session's egress policy (HTTP 403 on CONNECT); the docs **source** repository was used instead. | session log |

## 5. Runtime decision matrix (inference from the facts above)

| Option | Assessment |
| --- | --- |
| JavaScript Worker with the published WASM | **Not viable as published.** The build needs Worker threads and `Atomics.wait`, which `workerd` does not provide. A custom single-threaded build would block the isolate, lose interrupt support, must fit 128 MB with the solver heap, and has no upstream artifact to track. |
| Python Worker with the pyemscripten wheel | **Unproven.** The wheel exists and is single-threaded, but Pyodide version alignment (CPython 3.14), the 128 MB isolate limit and solver runtimes were not tested here, and the test would require a Cloudflare account. |
| Cloudflare Container running native Z3 | **Viable.** Native Linux x64 Z3 is verified locally; containers offer up to 4 vCPU / 12 GiB and are reachable only through a Worker binding, which is the required authenticated boundary. Requires the Workers Paid plan. |
| External container or VM service | **Viable.** Same software; the Worker calls it over an authenticated channel. |

**Decision:** the engine runs as a native Python service (this repository), behind an
authenticated Worker. The browser never reaches the solver. Deployment itself is
not performed in this repository.

## 6. Prior art

| Source | Reusable as | Not reusable as |
| --- | --- | --- |
| Upstream Z3 agent skills (`.github/skills/prove/scripts/prove.py`) | Design reference for negation-based validity checks and SQLite run logging. | Code: it accepts SMT-LIB text and checks validity by negation **without a premise-consistency check**, so inconsistent premises would read as "valid". This engine checks consistency first. |
| Upstream Z3 MCP server (`src/api/mcp/z3mcp.py`) | Awareness that Z3 ships an MCP entry point. | Not used. |
| `lovishchopra/NL2FOL` | Method inspiration: staged decomposition (claim → entities/properties → formula), grounding before formalization, counterexample framing (`docs/DESIGN_INSPIRATION.md`). | Code or prompts: research code targeting cvc4 with torch dependencies; MIT-licensed; nothing copied. |

## 7. Principal risks

- **Correctness:** vacuous entailment from inconsistent premises (mitigated: consistency first); Int/Real/float conflation (mitigated: strict sorts, string numerals); unknown/timeout read as success (mitigated: closed status taxonomy, `is_definitive`).
- **Interpretation drift:** a sound result about the encoding being read as truth of the claim (mitigated: scope statement on every result; translation interpretation and grounding reported separately; semantic review marked advisory).
- **Security:** executable content from a model (mitigated: IR is data, strict JSON parse, closed allowlist); agent self-certification (mitigated: advisory fields ignored, signed results, service rejects status fields); resource exhaustion (mitigated: limits, timeout, rlimit, body size, concurrency, rate limit).
- **Provenance:** reuse of a result for a modified representation (mitigated: binding digest over problem, config and versions).

## 8. Blocked or deferred items

- The missing specifications and the IB training pack (Phase 0 of the plan).
- No model-provider credentials in the session: model-backed providers are implemented but **untested live**.
- No Cloudflare account access: Worker and Container deployment are specified, not performed.
- The account's five-hour usage limit interrupted sub-agent runs once (reset 07:40 UTC); work resumed with model fallback.

## 9. Changes made during discovery

Outside the repositories: a scratchpad virtual environment with `z3-solver`, an npm
install of `z3-solver`, and a local `workerd` probe. Inside the repositories: only the
commits on branch `claude/z3-verification-engine-plan-nk3luq` in both repositories.
