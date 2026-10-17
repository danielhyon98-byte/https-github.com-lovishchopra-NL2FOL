// Kit W3 end to end (copied into the website's tests/ by integration/website/apply.mjs): POST /api/chat through
// handleRequest with the verified backend on loopback development, the node:sqlite D1, the simulation's specialist
// orchestrator over a fake runtime, and a fake checks service behind fetchImpl. No network, no provider.
import assert from "node:assert/strict";
import test from "node:test";

import { checksBadge } from "../public/chat-contract.js";
import { errorResult, statusForError } from "../src/chat/contract.js";
import { handleRequest } from "../src/index.js";
import { countClaims } from "../src/verify/decision-table.js";
import { createSpecialistOrchestrator } from "../src/verify/specialist-orchestrator.js";
import { createD1 } from "./helpers/d1.js";
import { vector } from "./kit-vectors.js";

const LOCAL = "http://127.0.0.1:8787";
const TOKEN = "kit-simulation-token-0123456789";
const VARS = Object.freeze({
  APP_ENV: "development", CHAT_BACKEND: "verified", CHAT_STATE: "d1", ROUTER_MODE: "mock", TRANSLATOR_MODE: "http",
  TRANSLATOR_BASE_URL: "http://127.0.0.1:8899", TRANSLATOR_SERVICE_TOKEN: TOKEN, KIT_SIMULATION: "1",
});
const RUNTIME = vector("specialist-port/v1", "answer");
const EXCERPT = "The Treaty of Versailles (1919) imposed reparations and territorial losses on Germany.";
const MESSAGE = "SYNTHETIC history question: how far did the Treaty of Versailles destabilise Germany in the 1920s?";

function claim(formal) {
  return { claim_id: "h1.1", materiality: "material", role: "point", excerpt: EXCERPT, source: "translation", formal, attempt: "attempted",
    fidelity: "missing", evidence_resolved: false, release_permitted: false, result_id: null, binding_digest: null };
}

// The fake checks service's verdict for one request, bound to it (the Worker holds no key: the signature's value is
// opaque to it). `mode` picks deliver, a blocking refusal, or a verdict bound to another attempt.
function verdictFor(req, mode) {
  const v = structuredClone(vector("verdict-binding", "deliver-bound").verdict);
  const a = req.answers[0];
  v.ids.task_id = req.ids.task_id;
  v.ids.request_id = mode === "tamper" ? "a_other_attempt_00000000" : req.ids.request_id;
  v.bound.user_text_sha256 = req.task.user_text_sha256;
  v.bound.answers = [{ agent_id: a.agent_id, answer_sha256: a.answer_sha256, result_sha256: a.result_sha256, report_id: "rep_t_history_v1", message_id: "m-1" }];
  if (mode === "refuse") {
    v.claims = [claim("COUNTEREXAMPLE")];
    v.delivery = { ...v.delivery, decision: "refuse_unresolved", reasons: ["KIT-DL-010"], deliverable: null };
    v.summary = null;
  } else if (mode === "invalid" || mode === "noclaims") {
    // delivered, but no material claim has a positive formal result: the summary is not_formally_checkable
    v.claims = mode === "invalid" ? [claim("INVALID_FORMALIZATION")] : [];
    v.delivery = { ...v.delivery, deliverable: { agent_id: a.agent_id, answer_sha256: a.answer_sha256, message_id: "m-1" } };
    v.summary = "not_formally_checkable";
  } else {
    v.claims = [claim("ENTAILED")];
    v.delivery = { ...v.delivery, deliverable: { agent_id: a.agent_id, answer_sha256: a.answer_sha256, message_id: "m-1" } };
    v.summary = "formal_only";
  }
  v.counts = countClaims(v.claims);
  return v;
}

function world({ vars = {}, service = "deliver", available = true, orchestrator = null } = {}) {
  const db = createD1();
  db.applyMigrations();
  const env = { ...VARS, CHAT_DB: db, ...vars };
  const logs = [];
  const calls = { capabilities: 0, check: 0, specialist: 0 };
  const caps = vector("handshake", "compatible").capabilities;
  const fetchImpl = async (url, init = {}) => {
    const u = new URL(typeof url === "string" ? url : url.url);
    assert.equal(u.hostname, "127.0.0.1", "the simulation fetches loopback only");
    assert.equal(init.headers?.Authorization, `Bearer ${TOKEN}`);
    if (u.pathname === "/v1/capabilities") {
      calls.capabilities += 1;
      if (service === "down") throw new Error("ECONNREFUSED");
      return Response.json(caps);
    }
    calls.check += 1;
    if (service === "error") return new Response("{}", { status: 500, headers: { "Content-Type": "application/json" } });
    return Response.json(verdictFor(JSON.parse(init.body), service));
  };
  const runtime = {
    getCapabilities: () => ({ specialists: [{ slug: "history", available }] }),
    runSpecialistTurn: async () => { calls.specialist += 1; return structuredClone(RUNTIME.result); },
  };
  const inner = createSpecialistOrchestrator({
    runtime, redactForLog: () => structuredClone(RUNTIME.log), bundleFor: async () => ({}), turnInputFor: () => ({}),
    failure: (rid, code) => ({ status: statusForError(code), result: errorResult(rid, code) }),
  });
  const chatOptions = { verified: { inner }, log: (entry) => logs.push(entry), ctx: { waitUntil: () => {} },
    ...(orchestrator ? { orchestrator } : {}) };
  async function post(body, { headers = {} } = {}) {
    const request = new Request(`${LOCAL}/api/chat`, { method: "POST", headers: { "Content-Type": "application/json", ...headers }, body: JSON.stringify(body) });
    const response = await handleRequest(request, env, fetchImpl, chatOptions);
    const text = await response.text();
    return { status: response.status, body: JSON.parse(text), headers: response.headers };
  }
  async function history(id) {
    const response = await handleRequest(new Request(`${LOCAL}/api/conversations/${id}`), env, fetchImpl, chatOptions);
    return response.json();
  }
  const one = (sql) => db.raw.prepare(sql).get();
  return { db, env, logs, calls, post, history, one };
}

const send = (clientTurnId = "turn_00000001") => ({ message: MESSAGE, clientTurnId });

test("a bound deliver verdict releases the answer with review checks:integration.v1, and a retry replays it", async () => {
  const w = world();
  const before = w.db.log.length;
  const r = await w.post(send());
  assert.equal(r.status, 200, JSON.stringify(r.body));
  assert.equal(r.body.review, "checks:integration.v1");
  assert.deepEqual(r.body.checks, [{ claim: EXCERPT, formal: "ENTAILED", fidelity: "missing" }]);
  assert.equal(r.body.checksSummary, "formal_only");
  assert.equal(r.body.text, RUNTIME.result.answer);
  assert.equal(r.headers.get("X-Chat-Backend"), "verified");
  assert.equal(r.headers.get("X-Chat-Simulated"), "1");
  assert.ok(w.db.log.length - before <= 36, `D1 statements per request: ${w.db.log.length - before}`);
  assert.deepEqual([w.calls.capabilities, w.calls.specialist, w.calls.check], [1, 1, 1]);
  assert.ok(w.logs.some((l) => l.event === "chat_check" && l.outcome === "answer"));
  assert.ok(w.logs.every((l) => !JSON.stringify(l).includes(MESSAGE) && !JSON.stringify(l).includes(EXCERPT)), "logs carry labels only");
  const again = await w.post(send());
  assert.equal(again.status, 200);
  assert.equal(again.headers.get("X-Chat-Replay"), "1");
  assert.deepEqual([w.calls.specialist, w.calls.check], [1, 1], "a replay makes no specialist or service call");
  const stored = await w.history(r.body.conversationId);
  assert.deepEqual(stored.turns[0].reply.checks, r.body.checks);
  assert.equal(w.one("SELECT simulated FROM turns").simulated, 1);
});

test("an answer delivered without a positive formal result is labelled not formally checked, never passed", async () => {
  for (const service of ["invalid", "noclaims"]) {
    const w = world({ service });
    const r = await w.post(send());
    assert.equal(r.status, 200, JSON.stringify(r.body));
    assert.equal(r.body.review, "checks:integration.v1");
    assert.equal(r.body.checksSummary, "not_formally_checkable", service);
    assert.deepEqual(checksBadge(r.body.checksSummary), ["Not formally checked", null], service);
    const stored = await w.history(r.body.conversationId);
    assert.equal(stored.turns[0].reply.checksSummary, "not_formally_checkable", "history replays the same summary, so the same badge");
    const formal = r.body.checks.map((c) => c.formal);
    assert.deepEqual(formal, service === "invalid" ? ["INVALID_FORMALIZATION"] : [], service);
  }
  const positive = await world().post(send());
  assert.deepEqual(checksBadge(positive.body.checksSummary), ["Automatic checks passed", "is-ok"]);
});

test("a refusing verdict is 422 review_unresolved, stored under its raw code and shown as the same public code", async () => {
  const w = world({ service: "refuse" });
  const r = await w.post(send());
  assert.deepEqual([r.status, r.body.code, r.body.retryable], [422, "review_unresolved", false]);
  assert.equal(w.one("SELECT error_code FROM turns").error_code, "kit_dl_010");
  const conv = w.one("SELECT id FROM conversations").id;
  const h = await w.history(conv);
  assert.equal(h.turns[0].errorCode, "review_unresolved");
  assert.equal(h.turns[0].reply, null, "nothing is stored as an answer");
});

test("a failed checks call is 503 checks_incomplete; a verdict for another attempt is 502 upstream_invalid", async () => {
  let w = world({ service: "error" });
  let r = await w.post(send());
  assert.deepEqual([r.status, r.body.code], [503, "checks_incomplete"]);
  assert.equal(w.one("SELECT error_code FROM turns").error_code, "verifier_error");
  w = world({ service: "tamper" });
  r = await w.post(send());
  assert.deepEqual([r.status, r.body.code], [502, "upstream_invalid"]);
  assert.equal(w.one("SELECT error_code FROM turns").error_code, "kit_dl_030");
});

test("the service down at the handshake is 503 service_unavailable with no specialist call", async () => {
  const w = world({ service: "down" });
  const r = await w.post(send());
  assert.deepEqual([r.status, r.body.code], [503, "service_unavailable"]);
  assert.equal(w.one("SELECT error_code FROM turns").error_code, "kit_hs_unreachable");
  assert.equal(w.calls.specialist, 0);
});

test("a subject unavailable after routing is 503 chat_unavailable with no specialist call", async () => {
  const w = world({ available: false });
  const r = await w.post(send());
  assert.deepEqual([r.status, r.body.code], [503, "chat_unavailable"]);
  assert.equal(w.one("SELECT error_code FROM turns").error_code, "specialist_unavailable");
  assert.deepEqual([w.calls.specialist, w.calls.check], [0, 0]);
});

test("an incomplete configuration is 503 chat_unavailable before admission: no turn is stored", async () => {
  const w = world({ vars: { TRANSLATOR_SERVICE_TOKEN: "" } });
  const r = await w.post(send());
  assert.deepEqual([r.status, r.body.code], [503, "chat_unavailable"]);
  assert.equal(w.one("SELECT count(*) AS n FROM turns").n, 0);
  assert.ok(w.logs.some((l) => l.event === "chat_check" && l.label === "kit_config:translator_token"));
});

test("a mock scenario header is refused, options.orchestrator is ignored, and the stateless path never runs it", async () => {
  let w = world();
  let r = await w.post(send(), { headers: { "X-Mock-Scenario": "auto" } });
  assert.deepEqual([r.status, r.body.code], [400, "invalid_mock_scenario"]);
  w = world({ orchestrator: { handle: async () => assert.fail("the mock orchestrator must not run under the verified backend") } });
  r = await w.post(send());
  assert.equal(r.status, 200);
  w = world({ vars: { CHAT_STATE: "none" } });
  r = await w.post(send());
  assert.deepEqual([r.status, r.body.code], [503, "chat_unavailable"]);
  assert.equal(w.calls.capabilities + w.calls.check, 0);
});
