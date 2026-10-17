// The verified backend's decorator and release gate (PROTOCOL.md section 9; website/PATCH-PLAN.md, W3), with a fake inner orchestrator and a fake checks
// client: an answer is released only from a bound verdict that says deliver, composed with review
// "checks:integration.v1" and checks that agree with the verdict; every other path names its raw code.
import assert from "node:assert/strict";
import test from "node:test";

import { countClaims } from "../src/verify/decision-table.js";
import { checksFromVerdict, releaseGate, VERIFIED_REVIEW } from "../src/verify/release-gate.js";
import { createSpecialistOrchestrator } from "../src/verify/specialist-orchestrator.js";
import { checksBudgetMs, withVerification } from "../src/verify/with-verification.js";
import { vector } from "./kit-vectors.js";

const runtime = vector("specialist-port/v1", "answer");
const ANSWER = runtime.result.answer;
const STATUS = { review_unresolved: 422, checks_incomplete: 503, upstream_invalid: 502, chat_unavailable: 503, turn_cancelled: 409 };
const failure = (requestId, code) => ({ status: STATUS[code] ?? 500, result: { kind: "error", requestId, code, message: code, retryable: false } });
// The decorator's outcome in the website's orchestrator contract, flattened for the assertions below.
const flat = (o) => ({ ...o.result, status: o.status, kit: o.kit });
const capabilities = (available = true) => ({ specialists: [{ slug: "history", available }] });

function innerFor({ available = true, result = runtime.result } = {}) {
  const calls = [];
  return {
    calls,
    capabilities: async () => capabilities(available),
    handle: async (request, context) => {
      calls.push(context.slug);
      return { specialist: { result, redacted: runtime.log, live: false } };
    },
  };
}

function verdictFor(req, edit = (v) => v) {
  const v = structuredClone(vector("verdict-binding", "deliver-bound").verdict);
  const a = req.answers[0];
  v.ids.task_id = req.ids.task_id;
  v.ids.request_id = req.ids.request_id;
  v.bound.user_text_sha256 = req.task.user_text_sha256;
  v.bound.answers = [{ agent_id: a.agent_id, answer_sha256: a.answer_sha256, result_sha256: a.result_sha256, report_id: "rep_t_history_v1", message_id: "m-1" }];
  v.delivery.deliverable = { agent_id: a.agent_id, answer_sha256: a.answer_sha256, message_id: "m-1" };
  v.claims = [];
  v.counts = countClaims([]);
  v.summary = "not_formally_checkable";
  return edit(v);
}

function setup({ verdict = (req) => verdictFor(req), call = null, inner = innerFor(), pending = () => true, deadlineIn = 120000 } = {}) {
  const sent = [];
  const verification = {
    client: { checkTurn: async (req) => { sent.push(req); return call ?? { ok: true, body: verdict(req) }; } },
    lastCapabilities: { ports: { translation: { live: false } } },
  };
  const orchestrator = withVerification(inner, { verification, failure, environment: "sim" });
  const context = { requestId: "req-1", route: { routeId: "history" }, turn: { turnId: "turn_00000001", attemptId: "attempt_00000001" },
    deadlineAt: Date.now() + deadlineIn, stillPending: async () => pending() };
  const request = { message: "SYNTHETIC: How far did the Treaty of Versailles destabilise Germany?", conversationId: "conv-1", expectedTurnVersion: 0 };
  return { orchestrator, context, request, sent, inner };
}

test("a bound deliver verdict releases the exact answer with review checks:integration.v1", async () => {
  const { orchestrator, context, request, sent } = setup();
  const out = flat(await orchestrator.handle(request, context));
  assert.equal(out.kind, "answer");
  assert.equal(out.text, ANSWER);
  assert.equal(out.review, VERIFIED_REVIEW);
  assert.deepEqual([out.checks, out.checksSummary], [[], "not_formally_checkable"]);
  assert.deepEqual([out.kit.rawCode, out.kit.simulated], [null, true]);
  const [req] = sent;
  assert.deepEqual([req.mode, req.policy, req.ids.task_id, req.ids.request_id, req.task.slug, req.task.route], ["single", "verified-v1", "turn_00000001", "attempt_00000001", "history", "history"]);
  assert.ok(req.budget_ms >= 3000 && req.budget_ms <= 65000);
  const released = { ...out };
  delete released.kit;
  delete released.status;
  assert.equal(releaseGate(out.kit.verdict, released), null);
  assert.equal(out.status, 200);
});

test("the checks show the formal statuses of material claims, never more than the verdict says", async () => {
  const excerpt = "The Treaty of Versailles (1919) imposed reparations and territorial losses on Germany.";
  const claim = { claim_id: "h1.1", materiality: "material", role: "point", excerpt, source: "translation", formal: "ENTAILED", attempt: "attempted",
    fidelity: "faithful", evidence_resolved: false, release_permitted: false, result_id: null, binding_digest: null };
  const { orchestrator, context, request } = setup({ verdict: (req) => verdictFor(req, (v) => ({ ...v, claims: [claim], counts: countClaims([claim]), summary: "formal_only" })) });
  const out = flat(await orchestrator.handle(request, context));
  assert.equal(out.checksSummary, "formal_only");
  assert.deepEqual(out.checks, [{ claim: excerpt, formal: "ENTAILED", fidelity: "without_evidence" }]); // faithful, but not established
});

test("a refusal of the checks is a closed error named by its first reason", async () => {
  const claim = { claim_id: "h1.1", materiality: "material", role: "point", excerpt: "The Treaty of Versailles (1919)", source: "translation",
    formal: "COUNTEREXAMPLE", attempt: "attempted", fidelity: "missing", evidence_resolved: false, release_permitted: false, result_id: null, binding_digest: null };
  const { orchestrator, context, request } = setup({ verdict: (req) => verdictFor(req, (v) => ({
    ...v, claims: [claim], counts: countClaims([claim]), summary: null,
    delivery: { ...v.delivery, decision: "refuse_unresolved", reasons: ["KIT-DL-010"], deliverable: null } })) });
  const out = flat(await orchestrator.handle(request, context));
  assert.deepEqual([out.kind, out.code, out.kit.rawCode], ["error", "review_unresolved", "kit_dl_010"]);
});

test("a verdict for another attempt, a malformed verdict and a failed call are refused by code", async () => {
  let r = setup({ verdict: (req) => verdictFor(req, (v) => ({ ...v, ids: { ...v.ids, request_id: "attempt_other" } })) });
  let out = flat(await r.orchestrator.handle(r.request, r.context));
  assert.deepEqual([out.code, out.kit.rawCode], ["upstream_invalid", "kit_dl_030"]);
  r = setup({ verdict: (req) => ({ ...verdictFor(req), verified: true }) });
  out = flat(await r.orchestrator.handle(r.request, r.context));
  assert.deepEqual([out.code, out.kit.rawCode], ["upstream_invalid", "verifier_malformed"]);
  r = setup({ call: { ok: false, code: "verifier_timeout" } });
  out = flat(await r.orchestrator.handle(r.request, r.context));
  assert.deepEqual([out.code, out.kit.rawCode], ["checks_incomplete", "verifier_timeout"]);
});

test("a subject that is unmapped or unavailable makes no specialist call", async () => {
  let r = setup({ inner: innerFor({ available: false }) });
  let out = flat(await r.orchestrator.handle(r.request, r.context));
  assert.deepEqual([out.code, out.kit.rawCode, r.inner.calls.length, r.sent.length], ["chat_unavailable", "specialist_unavailable", 0, 0]);
  r = setup();
  out = flat(await r.orchestrator.handle(r.request, { ...r.context, route: { routeId: "geography" } }));
  assert.deepEqual([out.code, out.kit.rawCode, r.inner.calls.length], ["chat_unavailable", "specialist_unmapped", 0]);
});

test("a cancelled attempt makes no checks call, and no time left means no call", async () => {
  let n = 0;
  let r = setup({ pending: () => (n += 1) < 2 });
  let out = flat(await r.orchestrator.handle(r.request, r.context));
  assert.deepEqual([out.code, r.sent.length], ["turn_cancelled", 0]);
  r = setup({ deadlineIn: 5000 });
  out = flat(await r.orchestrator.handle(r.request, r.context));
  assert.deepEqual([out.code, out.kit.rawCode, r.sent.length], ["checks_incomplete", "verifier_timeout", 0]);
  assert.equal(checksBudgetMs(Date.now() + 1000, Date.now()), null);
});

test("the release gate refuses passed or not_required, altered checks and a refusal shown as an answer", async () => {
  const { orchestrator, context, request } = setup();
  const out = flat(await orchestrator.handle(request, context));
  const verdict = out.kit.verdict;
  const result = { ...out };
  delete result.kit;
  delete result.status;
  assert.equal(releaseGate(verdict, { ...result, review: "passed" }).rawCode, "kit_gate_review");
  assert.equal(releaseGate(verdict, { ...result, review: "not_required" }).rawCode, "kit_gate_review");
  assert.equal(releaseGate(verdict, { ...result, checks: [{ claim: "x", formal: "ENTAILED", fidelity: "faithful" }] }).rawCode, "kit_gate_checks");
  assert.equal(releaseGate(verdict, { ...result, checksSummary: "formally_checked" }).rawCode, "kit_gate_checks");
  assert.equal(releaseGate({ ...verdict, delivery: { ...verdict.delivery, decision: "refuse_incomplete" } }, result).rawCode, "kit_gate_decision");
  assert.equal(releaseGate(verdict, { ...result, text: "x".repeat(70000) }).rawCode, "kit_gate_size");
  assert.deepEqual(checksFromVerdict(verdict), { checks: [], checksSummary: "not_formally_checkable" });
});

test("the simulation's specialist orchestrator refuses to build without its runtime", () => {
  assert.throws(() => createSpecialistOrchestrator({}), TypeError);
  assert.throws(() => withVerification(null, {}), TypeError);
});
