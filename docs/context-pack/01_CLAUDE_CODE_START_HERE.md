# Claude Code: Start Here — Epinoic AI Engineering Handoff

You are working on Epinoic AI, an educational multi-agent AI platform intended to tutor students across the International Baccalaureate (IB). Read `00_PROJECT_CONTEXT_AND_ARCHITECTURE.md` and the relevant files under `specifications/` before proposing architecture or modifying code.

The core implementation objective is a provider-independent, auditable tutoring infrastructure with subject-specialist agents, a router, a source-grounded retrieval layer, an information-preserving combinator, a restricted LLM-to-logic translator, a deterministic Z3 verification service, and an independent Overseer. The website and application are intended to integrate with Cloudflare. The system must be scalable through bounded work, queueing where appropriate, quotas, observability, and measurable load testing—not by assuming infrastructure can never overload.

The immediate task is **repository discovery and planning, not a wholesale rewrite**.

First inspect the repository and all relevant implementation and deployment files. Read the Z3 and Overseer specifications in full. Identify what exists, what works, what has tests, what is missing, and where the current implementation differs from the target architecture. Verify the configured language/runtime versions, model providers, Cloudflare bindings, database schema, queue configuration, authentication, and Z3 runtime compatibility rather than making assumptions.

Return a repository audit and a phased implementation plan before making substantial changes. Include the architecture/data-flow map, existing component inventory, gaps, key contracts, security boundaries, runtime compatibility, testing plan, dependencies, and unverified assumptions. Preserve working code and tests. Do not claim functionality exists without locating it in the repository.

After the audit is reviewed, implement incrementally. Establish versioned data contracts, immutable original specialist reports, stable request/task/claim IDs, explicit verification statuses, and provenance before attempting complex orchestration. Start the formal language with a small supported subset. Never execute arbitrary LLM-generated code. Keep deterministic checks in code and reserve LLM reviewing for questions requiring semantic judgment.

The Z3 engine must check only the formal representation it receives. It must never imply that a valid formal proof establishes that the original natural-language interpretation or factual premises are correct. The Overseer must never rely on an agent's self-reported verification status. Unknown, unsupported, invalid, ambiguous, timeout, and internal-error outcomes must never be represented as success. Conflicts and material claim omissions must not be silently hidden.

Optimize for low latency by routing narrowly, retrieving selectively, running independent necessary specialists concurrently, validating results as they arrive, bounding all calls and retries, and using code for schema, ID, and deterministic arithmetic checks. The application must have both a fast path for ordinary questions and a background-task path for long-running tasks. Do not bypass required checks merely to make the response faster.

Use Cloudflare Workers for suitable website/API/orchestration responsibilities, and choose appropriate compute for native Z3 and model inference. Do not assume all workloads can or should run inside a Worker. Keep API keys and private endpoints out of browser code.

For every implementation phase, run the relevant tests and report: files changed, actual tests run and outcomes, failures, remaining limitations, security or deployment requirements still outstanding, and next steps. Never delete/relax tests to hide failures; never claim production deployment without actual evidence.

Begin now with the audit and phased plan. Do not begin the full implementation during this first pass.
