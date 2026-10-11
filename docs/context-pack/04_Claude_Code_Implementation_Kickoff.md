# Epinoic AI — Claude Fable 5.1 / Claude Code Implementation Kickoff Prompt

Use this prompt together with `Epinoic_AI_Z3_Logic_Verification_Engine_Codex_Specification.md`.

---

You are working as the lead implementation engineer inside Claude Code, using Claude Fable 5.1. I am developing Epinoic AI, an educational multi-agent AI platform. The attached or repository-accessible file named `Epinoic_AI_Z3_Logic_Verification_Engine_Codex_Specification.md` is the detailed engineering specification for the Z3 Logic Verification Engine. Read that specification in full before proposing implementation changes. Although its filename mentions Codex, it is intended to be a model-independent engineering specification and must be applied here in Claude Code.

Your task is to implement the specification in the existing repository, not merely summarize it, rewrite it as another design document, or create a disconnected demonstration. However, you must work in controlled phases. Do not immediately rewrite the repository or modify large numbers of files before understanding how the existing system works.

## First phase: inspect and understand

Begin by inspecting the repository, its directory structure, source files, dependency manifests, tests, configuration, deployment files, and existing agent/knowledge-document instructions. Identify the current application stack and determine which elements of Epinoic AI are already implemented. Specifically investigate any existing frontend, backend, Cloudflare Workers configuration, authentication, database, document ingestion and retrieval, model-provider adapters, agent router, subject specialists, combinator, overseer, Z3 integration, task queue, logging, and test infrastructure.

Read the entire Z3 specification and compare it with the implementation you actually find. Do not assume that a component exists simply because it is mentioned in documentation. Do not assume that an unimplemented component can safely be replaced without affecting other parts of the application. Preserve working behavior and existing interfaces unless there is a documented technical reason to change them.

If the specification file is not available in the repository or as an accessible attachment, stop and clearly identify the missing file. Do not fabricate its contents or claim to have read it. If it is available, confirm which file you read and use it as the governing requirements document.

During this first phase, do not make broad code changes. Produce a repository audit and an implementation plan. Explain the current request flow, the components that exist, the components that are missing, the main security and correctness risks, and the dependencies between implementation stages. Distinguish verified facts from assumptions. Identify any requirements that conflict with the current architecture and propose the least disruptive resolution.

## Second phase: establish the implementation plan

After the audit, propose a sequence of small, testable implementation stages. The plan must cover formal request and response contracts; the restricted intermediate representation; type and schema validation; the deterministic Z3 compiler; satisfiability, consistency, entailment, and counterexample procedures; the LLM translation adapter; provenance and claim tracking; overseer integration; authenticated service APIs; Cloudflare integration; security controls; observability; performance; and automated testing.

For each stage, state its purpose, required code changes, dependencies, tests, acceptance criteria, and remaining risks. Start with the smallest reliable end-to-end path. Do not implement all advanced features at once. Prefer a correct, narrowly scoped formal language over a broad but unreliable natural-language-to-logic system.

Once the audit and phased plan are complete, wait for my approval before making broad implementation changes. You may make a small, clearly justified discovery or test-only change if it is essential to confirm a technical fact, but report it before proceeding.

## Core engineering requirements

The detailed specification is authoritative for the intended behavior. The most important distinction is that a successful Z3 result proves a property of the formal representation under its encoded premises; it does not independently prove that the original natural-language claim was interpreted correctly or that the premises are factually true. Preserve this distinction in types, statuses, API contracts, logs, documentation, and overseer decisions.

Do not build a supposed universal hallucination detector. Build a restricted, auditable verification service that states exactly what it checked, how it checked it, which assumptions were used, which sources were referenced, and what remains unresolved. Formal logical claims may be eligible for Z3. Factual claims must be routed to evidence-based checks, and qualitative educational judgments must be evaluated using appropriate subject-specific rules. Do not attempt to encode every History, English, or Business Management judgment as a formal theorem.

The LLM translator must output a typed, versioned abstract syntax tree conforming to a restricted schema. It must never submit arbitrary executable code to the solver. Implement a deterministic compiler whose supported AST operators are explicitly allowlisted. Reject undeclared variables, incompatible sorts, unknown operators, unapproved fields, malformed expressions, unsupported theories, oversized inputs, and excessive nesting. Use exact arithmetic where the selected formal domain requires it. Do not conflate integer, real, and floating-point semantics.

For entailment, check premise consistency first. If the premises are inconsistent, return a distinct `INCONSISTENT_PREMISES` result. When premises are consistent, check whether the premises together with the negation of the conclusion are satisfiable. An unsatisfiable result can establish entailment under the encoded assumptions; a satisfiable result can provide a counterexample. Unknown results, timeouts, unsupported expressions, invalid formalizations, and service errors must never be represented as successful verification.

Every result must be bound to the exact request, original claim, formal representation, premises, conclusion, compiler and policy version, and solver configuration that produced it. If the representation changes, a previous verification result must not be reused as though it covered the modified representation. Never allow a specialist to self-certify its output. The independent overseer must obtain verification status from the appropriate service.

Preserve the original specialist reports immutably. Maintain stable claim IDs and source provenance. Ensure the combinator does not silently drop, rewrite, deduplicate away, or reconcile material claims without recording the transformation. Make unresolved contradictions visible. Structural checks must be deterministic wherever possible; semantic checks must be explicit about their limitations.

## Runtime and Cloudflare requirements

Inspect the actual runtime configuration before deciding where Z3 runs. Do not assume standard Z3 Python bindings will run in a Cloudflare Worker just because the application uses Cloudflare. If native Z3 execution is not demonstrably supported in the target runtime, place the solver behind a separate authenticated service using a compatible runtime and connect it to the Cloudflare-hosted backend through a bounded service interface.

The browser must never call the internal solver directly or receive unrestricted model-provider credentials. Enforce authentication, authorization, request-size limits, timeouts, concurrency controls, and rate limits. Keep secrets out of frontend code, source control, and client-visible errors. Use the existing stack where it is appropriate. Do not introduce a new framework or replace a working database without explaining the need and consequences.

Make independent specialist calls concurrent only when they are truly independent, and use bounded concurrency rather than unbounded parallel execution. Avoid LLM calls for deterministic tasks such as JSON schema validation, ID matching, exact arithmetic that can be checked by code, or verification-result binding. Use a low-latency path for simple requests and a controlled background-job path for longer tasks. Bound retries, solver duration, translation calls, token budgets, and total task duration. When a mandatory check cannot finish, report an unresolved result rather than bypassing verification.

## Testing and evidence of completion

Build tests as you implement each phase. Include unit tests for AST validation and compilation; tests for satisfiable and unsatisfiable premises; entailment tests; counterexample tests; tests for inconsistent premises; tests for unsupported operations; timeout and error handling; tests for malformed or malicious ASTs; source-provenance tests; tests for modified representations invalidating old results; tests for agent self-certification attempts; and end-to-end tests through the service boundary.

Do not delete or weaken existing tests just to make the new code pass. Run relevant test commands and report the actual outcomes. Where a test cannot be run, explain why and provide the exact command needed. Do not claim live Cloudflare deployment or real-provider integration unless it has actually been performed.

Record request IDs, claim IDs, relevant component versions, per-stage latency, timeouts, retry counts, solver result categories, and error types, while minimizing the storage of sensitive student content. Use realistic load tests and measure throughput, tail latency, queue depth, error rate, solver duration, model-token usage, and cost per completed request. Do not claim arbitrary scalability or zero hallucinations.

## How you should work in Claude Code

Operate as a careful senior engineer. Before editing a file, inspect the surrounding implementation and follow repository conventions. Make small cohesive changes rather than broad rewrites. Keep the implementation aligned with the specification and existing code. When a requirement is ambiguous, first inspect the code and available documentation; then state the ambiguity and choose the safest reversible design. Do not invent dependencies, API fields, environment variables, or Cloudflare capabilities without verifying them.

Maintain or create a concise `CLAUDE.md` only if the repository would benefit from persistent project-specific instructions. It should direct future sessions to the master specification, current architecture documents, test commands, safety boundaries, and implementation status. Do not duplicate the entire specification into `CLAUDE.md`.

After each approved implementation stage, summarize the files changed, behavior implemented, tests actually executed, results, known limitations, security implications, and next step. Update documentation to match the actual code. Keep a clear distinction between implemented, tested, deployed, and merely planned functionality.

The immediate task is to read the master specification and audit the repository. Do not begin with an unreviewed full implementation. Return the audit and phased plan first.

---

## User workflow

1. Open the Epinoic AI repository in Claude Code.
2. Select Claude Fable 5.1 if it is available in your Claude Code account and configuration.
3. Make the master Z3 specification available in the repository root or as an accessible project attachment.
4. Paste the prompt above into Claude Code.
5. Review the repository audit and implementation plan before authorizing code changes.
6. After approving the plan, instruct Claude Code to implement only the first stage and run its tests before continuing.
