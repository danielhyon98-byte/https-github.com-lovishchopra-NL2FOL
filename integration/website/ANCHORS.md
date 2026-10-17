# Anchors of the website patch set (base M: website `main` = `2cd3182`)

Every anchor occurs exactly the number of times given, in its file, at the pinned base (counted by the kit at build
time on an export of `2cd3182`). `apply.mjs` counts each one in the target before it writes anything and refuses
when a count differs (`anchor not found` / `anchor not unique`), and the playbook then stops (step 10);
`readiness/check-website.mjs --anchors <export>` prints the same counts. `src/index.js` (with `STAGING_ASSETS`) and
`src/state/sql.js` are not changed: the kit adds no public file, and `attemptPending` reuses `SQL.readAttempt`.

| File | Anchor (exact text) | Count | Step | Block |
|---|---|---|---|---|
| `public/chat-contract.js` | `export const REVIEW_STATES = Object.freeze(["passed", "not_required"]);` | 1 | W1 | 01-w1-review-states |
| `public/chat-contract.js` | `  answer: Object.freeze(["kind", "requestId", "conversationId", "turnVersion", "specialist", "text", "references", "review"]),` | 1 | W1 | 02-w1-result-fields |
| `public/chat-contract.js` | `if (!REVIEW_STATES.includes(result.review)) return "review";` | 1 | W1 | 03-w1-checks-after-review |
| `public/chat-contract.js` | `  answer: Object.freeze(["kind", "specialist", "text", "references", "review"]),` | 1 | W1 | 04-w1-reply-fields |
| `public/chat-contract.js` | `    : { kind: "answer", requestId: "history", conversationId, turnVersion, specialist: reply.specialist, text: reply.text, references: reply.references, review: reply.review };` | 1 | W1 | 05-w1-reply-checks |
| `src/chat/history.js` | `  return { kind: "answer", specialist: result.specialist, text: result.text, references: result.references, review: result.review };` | 1 | W1 | 06-w1-history-reply |
| `src/chat/history.js` | `import { ERROR_CODES, errorResult, statusForError } from "./contract.js";` | 1 | W1 | 07-w1-history-import |
| `src/chat/history.js` | `function publicTurnCode(code) {` | 1 | W1 | 08-w1-history-public-code |
| `src/chat/contract.js` | `  internal_error: [500, false, "The server hit an error while preparing the reply."],` | 1 | W1 | 09-w1-errors |
| `public/chat-logic.js` | `const ERROR_COPY = Object.freeze({` | 1 | W1 | 10-w1-error-copy |
| `public/chat-logic.js` | `    review: result.review,` | 1 | W1 | 11-w1-interpret-checks |
| `public/chat.js` | `  const simulated = outcome.mock ? " (simulated)" : "";` | 1 | W1 | 12-w1-simulated-label |
| `public/chat.js` | `const badges = [outcome.review === "passed"` | 1 | W1 | 13-w1-badges |
| `public/chat.js` | `  item.append(page);` | 1 | W1 | 14-w1-render-checks-call |
| `public/chat.js` | `function addAnswer(outcome, into = ui.messages) {` | 1 | W1 | 15-w1-render-checks |
| `public/chat.js` | `outcome.mock = response.headers.get("X-Chat-Backend") === "mock";` | 1 | W1 | 16-w1-simulated-header |
| `public/chat.js` | `import { CHAT_LIMITS, checkTitle, countCharacters, formatNumber } from "./chat-contract.js";` | 1 | W1 | 17-w1-chat-import |
| `src/chat/handler.js` | `import { createChatStore } from "../state/store.js";` | 1 | W3 | 20-w3-handler-imports |
| `src/chat/handler.js` | `export function chatBackendMode(url, env, access = null) {` | 1 | W3 | 21-w3-backend-mode |
| `src/chat/handler.js` | `if (backend === "mock") headers["X-Chat-Backend"] = "mock";` | 1 | W3 | 22-w3-backend-header |
| `src/chat/handler.js` | `if (backend !== "mock") return fail("chat_unavailable");` | 1 | W3 | 23-w3-backend-gate |
| `src/chat/handler.js` | `const scenario = request.headers.get("X-Mock-Scenario") ?? "auto";` | 1 | W3 | 24-w3-scenario |
| `src/chat/handler.js` | `const orchestrator = options.orchestrator ?? createMockOrchestrator();` | 1 | W3 | 25-w3-orchestrator |
| `src/chat/handler.js` | `const store = options.store ?? createChatStore(env.CHAT_DB);` | 1 | W3 | 26-w3-config-check |
| `src/chat/handler.js` | `const turn = runPersistentTurn({` | 1 | W3 | 27-w3-turn-args |
| `src/chat/handler.js` | `    if (typeof outcome.rawBody === "string") {` | 1 | W6 | 28-w6-check-log |
| `src/chat/turn.js` | `store, principal, request, requestId, scenario, routing, orchestrator, deadlineMs = TURN_DEADLINE_MS,` | 1 | W3 | 30-w3-turn-signature |
| `src/chat/turn.js` | `// 1. Route.` | 1 | W3 | 31-w3-turn-ready |
| `src/chat/turn.js` | `{ requestId, scenario, signal, route, routing: routing.mode },` | 1 | W3 | 32-w3-turn-context |
| `src/chat/turn.js` | `if (typeof outcome?.rawBody === "string") {` | 1 | W3 | 33-w3-turn-raw-body |
| `src/chat/turn.js` | `return failWith(result.code, { status: outcome.status, result });` | 1 | W3 | 34-w3-turn-raw-code |
| `src/chat/turn.js` | `    if (problem) return failWith("internal_error", failure(requestId, "internal_error"));` | 1 | W3 | 35-w3-turn-gate |
| `src/chat/turn.js` | `simulated: true` | 1 | W3 | 36-w3-turn-simulated |
| `src/state/store.js` | `return { admitTurn, recordRoute, completeTurn, failTurn, cancelTurn, listConversations, getConversation, renameConversation, deleteConversation };` | 1 | W3 | 37-w3-store-pending |
| `wrangler.jsonc` | `"ROUTER_MODE": "mock"` | 3 | W4 | 40-w4-wrangler-vars |
| `.dev.vars.example` | `ENABLE_OPENAI_TEST="false"` | 1 | W4 | 41-w4-dev-vars |
| `src/disclosure.js` | `export const CHAT_PAGE_PATHS = Object.freeze(["/dev/chat", "/dev/chat/", "/dev/chat/index.html"]);` | 1 | W4 | 42-w4-disclosure-anchors |
| `src/disclosure.js` | `if (env.ROUTER_MODE !== "live" \|\| (request.method !== "GET" && request.method !== "HEAD")) return env.ASSETS.fetch(request);` | 1 | W4 | 43-w4-disclosure-gate |
| `src/disclosure.js` | `  for (const [from, to] of ANCHORS) {` | 1 | W4 | 44-w4-disclosure-loop |
