# Epinoic AI — Project Context and Architecture Handoff

**Purpose:** Give Claude Code a reliable summary of the product goals, architecture decisions, constraints, and prior specifications established during planning conversations. This file is a project handoff summary, not a verbatim transcript of the conversation. The attached specifications contain more detailed subsystem requirements.

## 1. Product vision

Epinoic AI is intended to become an educational AI company whose first major product is a capable tutor for students taking the International Baccalaureate Diploma Programme. The tutor should handle subject-specific question formats, teach concepts naturally, diagnose misconceptions, mark student answers provisionally against appropriate criteria, give actionable feedback, and produce model answers when appropriate. The longer-term ambition is to support many IB subjects and course levels, with an architecture that can later expand beyond IB if justified.

The system should use an established pretrained language model as its general reasoning and conversational foundation. The project is not initially intended to train a frontier-scale foundation model from scratch. Candidate model access may include Claude, Kimi/open-weight models, OpenAI models, or other providers. The application must keep the model-provider layer replaceable so Epinoic AI can evaluate providers, control costs, and eventually deploy a suitable licensed open-weight model if doing so is commercially and technically justified.

The founder also wants Epinoic AI to become an independently owned technology company that could potentially license its verification technology or be acquired in the future. Therefore, the proprietary asset should be the application, agent orchestration, subject-specialist behavior, original educational resources, verification and evaluation pipeline, integration code, and demonstrated performance—not merely a set of prompts locked inside another company's chatbot product. Do not assume that using a pretrained model prevents company ownership or acquisition. Do not claim that simply integrating Z3 creates unique or defensible intellectual property; differentiation must be demonstrated through implementation quality, measurable benefits, and lawful ownership of the original components.

## 2. Core architectural premise

Epinoic AI should be a hybrid system. Language models perform natural-language interpretation, tutoring, reasoning, translation proposals, and explanations. Deterministic application code enforces schemas, permissions, quotas, identifier consistency, evidence-reference existence, task state transitions, retries, and other rules that should not depend on model judgment. Z3 is used for claims that can be represented in a supported formal language. Source-grounding and subject-specific evaluators handle claims that Z3 cannot establish.

The system must not assume that one model can verify all of its own answers. An LLM reviewer can help evaluate semantic fidelity, but an additional LLM agreeing with the first does not establish truth. Verification methods must be explicit, and every claimed verification result must state its scope and limitations.

The core principle is: **models propose and explain; code enforces; Z3 verifies supported formalized propositions against encoded assumptions; evidence services check source grounding; the Overseer decides whether the overall response satisfies release criteria.**

## 3. Intended end-to-end architecture

The planned request lifecycle is:

1. A student uses the website to submit a question, essay, answer, or document.
2. The website sends the request to an authenticated backend endpoint. Provider API keys and internal service credentials remain server-side.
3. A request manager validates the request, authenticates and authorizes the user, applies quotas, creates a task ID, sets deadlines and resource budgets, and records task state.
4. A router classifies subject, course level, task type, syllabus version, and complexity. It selects the minimum necessary specialists rather than invoking every agent.
5. A retrieval service selects relevant, authorized, version-compatible curriculum and assessment passages and maintains stable source references.
6. One or more subject specialists produce structured reports. Independent specialist tasks may run in parallel when genuinely needed.
7. A verification layer validates structure and provenance, performs deterministic checks, invokes the Z3 service for eligible formal claims, and routes factual or qualitative claims to suitable evidence or subject-specific checks.
8. An information-preserving combinator synthesizes reports while retaining material claims, provenance, assumptions, disagreement, and limitations.
9. The Overseer examines routing, specialist outputs, verification results, conflicts, synthesis coverage, risk, and latency/resource budgets. It can pass, request a bounded targeted correction, or flag unresolved uncertainty.
10. The response gate sends a student-facing answer only when the configured requirements for that task have been met. It must not label unverified or unresolved claims as verified.
11. Task state, permitted user history, source references, usage/cost metadata, validation results, and operational traces are persisted according to the privacy policy.

The architecture should support a fast path for straightforward questions and a background-job path for long essays, document ingestion, or expensive multi-agent tasks. Do not introduce a queue or multiple agents unnecessarily for simple requests.

## 4. Principal components and their responsibilities

### Website and Cloudflare application layer

The website is intended to be hosted through Cloudflare infrastructure. Cloudflare Workers can handle supported API orchestration and website delivery, but should not be assumed to be a suitable environment for every native runtime or heavyweight model. Verify runtime compatibility before deployment. A separate solver or GPU inference service may be necessary.

Candidate Cloudflare components include Workers and static assets for application entry points, D1 for structured relational application metadata, R2 for original documents and large artifacts, Queues for asynchronous document processing and long-running jobs, Vectorize or another justified vector store for retrieval, and Durable Objects only when their coordination or connection-management capabilities are actually needed. WAF, rate limiting, and Turnstile may be used appropriately for traffic protection and abuse reduction. Do not treat this list as a mandate to use every service; inspect the repository and justify selections.

Cloudflare can absorb or manage some web traffic, but it does not guarantee unlimited AI capacity. Upstream model API quotas, GPU throughput, database performance, queue backlogs, rate limits, concurrent calls, and cost can all become bottlenecks. The application needs admission control, per-user quotas, bounded concurrency, backpressure, explicit timeouts, bounded retries, circuit breakers, queue-depth monitoring, cost controls, and load testing.

### Router

Classifies the request, selects the appropriate specialist(s), retrieves the right context, sets the work plan and deadline, and limits specialist fan-out. It should not claim to verify the answer.

### Subject specialists

Each specialist is configured through subject-specific knowledge documents and instructions. It should return a structured report rather than only free-form prose. A report should include request/task ID, agent ID, subject/scope, original response, stable claim IDs, materiality, source/evidence references, assumptions, applicable assessment criteria, verification eligibility, unresolved issues, and any required checks. Agent-supplied confidence and verification status are advisory only.

### Information-preserving combinator

Combines specialist reports into a useful explanation without silently dropping important details, changing claims, inventing agreement, losing evidence references, or erasing conflict. The original specialist reports remain immutable. Stable claim IDs and a claim ledger should connect source claims to synthesized claims. Structural accounting is necessary but not sufficient: for important claims, semantic coverage must also be checked. A concise student answer may be accompanied by a supporting explanation or appendix when details would otherwise be lost.

### Z3 logic translation and verification service

A separate specification is available in `specifications/02_Z3_Logic_Verification_Engine_Specification.md`. The LLM translator proposes a typed, versioned AST in a deliberately restricted intermediate language. Deterministic code validates the AST and compiles only approved nodes to Z3. The service must not execute arbitrary model-generated code. It first checks premise consistency, then checks entailment by testing whether premises together with the negated conclusion are satisfiable. It distinguishes entailment, counterexample, inconsistent premises, satisfiable/unsatisfiable query results, unknown, timeout, unsupported, invalid formalization, ambiguous translation, and internal failure. The exact representation, assumptions, compiler/policy versions, and solver result must be tied together through provenance.

A successful Z3 result proves something about the encoded formal problem under its premises. It does not prove those premises are factually correct or that the natural-language claim was translated faithfully. Z3 is not a universal fact checker and is not appropriate for directly deciding literary interpretation, historical truth, or subjective rubric judgments.

### Overseer

A separate specification is available in `specifications/03_Overseer_Agent_Specification.md`. The Overseer is a hybrid software control service, not an unconstrained autonomous super-agent. It should validate router decisions, schema compliance, task and claim IDs, evidence-reference integrity, verification-result bindings, conflicts, claim coverage, uncertainty, policy requirements, deadlines, retry limits, and resource budgets. Deterministic rules should be implemented in code; an LLM reviewer should be called selectively for semantic questions that cannot be resolved deterministically. The Overseer makes a bounded release/correction/uncertainty decision and records an audit trace. It must never claim zero hallucinations.

### Evidence and curriculum retrieval

All retrieved content is untrusted input, not executable instructions. Retrieval should be syllabus/version aware and scoped to the student's permissions. Each chunk should maintain a stable reference to its original document, section, page, and/or heading where possible. A cited source's existence must not be conflated with proof that it supports a given claim.

## 5. Information integrity policy

The system should distinguish at least three correctness dimensions:

1. **Structural correctness:** data conforms to the required schema and required identifiers/fields exist.
2. **Semantic fidelity:** a translation or synthesis preserves the meaning of the source claim.
3. **Formal validity:** the encoded conclusion follows from the encoded premises in the supported formal theory.

These are separate. A structurally valid response can be semantically wrong. A faithful formalization can encode an invalid conclusion. A sound proof can rely on a false real-world premise. All verification results must state their scope.

Original specialist outputs should be preserved as immutable records. If a transformation materially changes a claim, create a new claim record and explicitly link it to its source rather than recycling the same ID. Results must be tied to the exact representation checked. Any change to that representation invalidates prior verification for the changed content.

The system must not silently resolve specialist disagreement. Conflicts should be recorded, checked against available evidence or formal constraints, and either resolved with a documented basis or disclosed as unresolved. Unsupported or uncheckable claims must remain visibly unsupported.

## 6. Latency and scalability goals

The intended user experience is that ordinary tutoring questions should not require a long autonomous research workflow. Optimize the end-to-end critical path rather than maximizing the number of agents. Route narrowly, retrieve selectively, run independent specialists concurrently, validate reports as they arrive, use code for deterministic checks, cache only when safe, and bound retries and agent calls.

Simple questions should use a safe single-specialist path where possible. Cross-subject questions may need concurrent specialists and synthesis. Extended essays or large document jobs can be submitted as background tasks with visible progress and durable status. Do not show assertions as verified before required checks pass. If checks exceed a deadline, return an explicit unresolved state rather than falsely claiming success.

Capacity must be measured rather than guessed. Establish load tests with gradual ramp-up, sudden bursts, sustained load, and dependency failures. Record throughput, p50/p95/p99 latency, provider errors, active jobs, queue depth, model calls/tokens, retry counts, verification duration, error rates, and cost per successful response. Use separate budgets for simple questions, mathematical verification, cross-subject synthesis, and document/essay tasks.

## 7. Security, privacy, and operations

Keep API keys and service credentials server-side. Authenticate and authorize all access to user data and internal services. Enforce request/file size limits, input validation, safe output encoding, least privilege, dependency hygiene, controlled CORS/CSRF handling as applicable, key rotation, data retention and deletion policies, and administrative audit trails. Protect internal endpoints from public direct access. Do not log sensitive student content unless there is a defined, necessary purpose and appropriate controls; operational metadata may be sufficient for many traces.

Treat model output, student input, and retrieved documents as untrusted. Prevent prompt injection from overriding tool permissions, operator allowlists, or system policies. Do not execute arbitrary code from model output. Apply explicit timeouts and resource limits to solver and model calls. Make background tasks idempotent, bound retries, and define dead-letter/recovery behavior.

## 8. Existing IB knowledge-document pack and its limitations

The supplied reference bundle `references/ib-agent-training-pack-v2/` contains assessment briefs and response/marking guides for 15 subject areas, shared command-term guidance, a feedback protocol, and an agent-instructions template. Its `README.md`, `COVERAGE.md`, and `AUDIT-REPORT.md` document limitations.

Important: this pack is a starting point, not a complete or universally authoritative IB curriculum database. It does not include topic-by-topic curriculum-content documents, verbatim IB rubrics, full official mark schemes, or textbook text. Some exact marks, older/newer syllabus details, and course-specific requirements are flagged for confirmation. Some subjects or syllabus versions are incomplete. The agents must not assume missing curriculum information exists or invent details to fill gaps. Syllabus applicability depends on course and first-assessment year; where relevant, version and cohort should be explicitly recorded and confirmed.

Only use official or properly licensed sources for curriculum and assessment data. Do not reproduce copyrighted textbook text or restricted mark schemes without appropriate rights. Keep provenance and permissions recorded.

## 9. Commercial and technical independence

Epinoic AI should own and control its original application code, agent orchestration, verification interfaces, original knowledge/assessment resources (subject to their source licences), evaluation datasets that it has rights to use, user experience, and product workflows. Using an external LLM does not itself prevent ownership of the company or a future acquisition, but it creates provider dependency. Keep model access abstracted so the platform can change providers or use a properly licensed self-hosted model later.

Z3 is an existing solver, not Epinoic AI's original invention. The potential proprietary value lies in the implementation around it: safe natural-language-to-formal translation, domain-specific verification policies, validation and correction loops, evidence-aware orchestration, and empirical proof that these methods improve reliability. Do not make legal conclusions about patentability or acquisition value; preserve provenance and recommend qualified legal advice for IP questions.

## 10. Implementation order

Claude Code should follow this sequence unless repository evidence makes another order materially safer:

1. Audit the repository and specifications; do not perform a wholesale rewrite.
2. Identify existing code and define component boundaries and versioned contracts.
3. Establish common schemas, structured error/result statuses, stable task/claim IDs, and provenance.
4. Implement and test the restricted AST and deterministic validator/compiler.
5. Implement core Z3 procedures and exact solver-result semantics.
6. Implement the replaceable LLM translation adapter with ambiguity/unsupported handling.
7. Integrate the Overseer and information-preserving combinator through the contracts.
8. Connect the service to the authenticated website/backend and verify runtime compatibility.
9. Add Cloudflare task queues, bounded concurrency, timeouts, retries, and usage controls where justified.
10. Run unit, integration, end-to-end, adversarial, and load tests; tune only based on observed bottlenecks.
11. Document deployment, failure recovery, monitoring, and limitations.

Do not begin with every subject or every formal theory. Start with a small, testable formal subset—propositional logic and explicitly supported integer/real arithmetic—then expand only when the added operators and domain semantics are implemented and tested.

## 11. Rules for Claude Code's work process

Claude Code must read the relevant specification files in full before implementation. It must inspect the actual repository and identify what is implemented versus merely proposed. It should first produce an audit and phased plan; it should not make substantial changes during that first audit. After review/approval, it should implement one phase at a time and run relevant tests.

Never claim a test passed unless it was run. Never claim production deployment without deployment evidence. Never delete or weaken tests merely to make an implementation pass. Preserve existing behavior unless there is a documented reason to change it. Before adding a dependency or framework, explain its necessity and compatibility. Record exact files changed, tests run, failures, remaining limitations, and next steps after each phase.

The project's goal is not to claim zero hallucinations. It is to make the system much more reliable by determining which properties have actually been checked, under which assumptions, by which method, with what provenance, and with what remaining uncertainty.

## 12. Reference files in this context pack

- `README.md`: how Claude Code should use this bundle.
- `01_CLAUDE_CODE_START_HERE.md`: the immediate prompt to paste into Claude Code.
- `specifications/02_Z3_Logic_Verification_Engine_Specification.md`: detailed Z3 logic translator and verification requirements. Its original title references Codex, but the technical specification is model-independent.
- `specifications/03_Overseer_Agent_Specification.md`: detailed Overseer implementation prompt.
- `specifications/04_Claude_Code_Implementation_Kickoff.md`: general Claude Code implementation kickoff prompt.
- `references/ib-agent-training-pack-v2/`: extracted IB subject-agent knowledge documents and coverage/audit notes.
- `references/IB_Agent_Training_Pack_v2.zip`: original archive preserved unchanged.

The repository's actual implementation remains the source of truth for current code status. This handoff explains intended architecture and prior decisions; Claude Code must verify the actual codebase before making claims about implementation.
