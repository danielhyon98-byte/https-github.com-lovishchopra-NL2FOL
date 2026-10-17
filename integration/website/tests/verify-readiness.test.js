// The verified backend's readiness (PROTOCOL.md section 3, checks 3 and 4; website/PATCH-PLAN.md, W2): the configuration check is synchronous, the
// handshake is cached for 60 s by an injected clock, a stale cache refreshes once, and a refresh failure leaves the
// backend not ready. The flash router is reported, never required.
import assert from "node:assert/strict";
import test from "node:test";

import { createVerification, evaluateCapabilities, workerEnvOf } from "../src/verify/verification.js";
import { vector } from "./kit-vectors.js";

const TOKEN = "kit-test-token-0123456789";
const env = (extra = {}) => ({ TRANSLATOR_MODE: "http", TRANSLATOR_BASE_URL: "http://127.0.0.1:8899", TRANSLATOR_SERVICE_TOKEN: TOKEN, KIT_SIMULATION: "1", ...extra });
const inner = { handle: async () => ({}) };
const caps = () => structuredClone(vector("handshake", "compatible").capabilities);
const ok = (body) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });

test("the configuration check names the first missing part", () => {
  assert.equal(createVerification({ env: env(), inner }).configProblem(), null);
  assert.equal(createVerification({ env: env({ TRANSLATOR_MODE: "none" }), inner }).configProblem(), "translator_mode");
  assert.equal(createVerification({ env: env({ TRANSLATOR_MODE: undefined }), inner }).configProblem(), "translator_mode");
  assert.equal(createVerification({ env: env({ TRANSLATOR_BASE_URL: "http://checks.example.test" }), inner }).configProblem(), "translator_url");
  assert.equal(createVerification({ env: env({ TRANSLATOR_SERVICE_TOKEN: "short" }), inner }).configProblem(), "translator_token");
  assert.equal(createVerification({ env: env({ TRANSLATOR_MODE: "binding" }), inner }).configProblem(), "translator_binding");
  assert.equal(createVerification({ env: env() }).configProblem(), "inner_orchestrator");
  assert.equal(createVerification({ env: env(), inner, base: "P" }).configProblem(), "timing");
});

test("a compatible handshake is cached for 60 s; a stale cache refreshes exactly once", async () => {
  let now = 1_000_000;
  let calls = 0;
  const v = createVerification({ env: env(), inner, now: () => now, fetchImpl: async () => { calls += 1; return ok(caps()); } });
  assert.equal((await v.ready()).ok, true);
  now += 59_000;
  assert.equal((await v.ready()).ok, true);
  assert.equal(calls, 1);
  now += 2_000;
  assert.equal((await v.ready()).ok, true);
  assert.equal((await v.ready()).ok, true);
  assert.equal(calls, 2);
  assert.equal(v.lastCapabilities.ports.router.required, false);
});

test("a refresh failure leaves the backend not ready, and the next turn tries again", async () => {
  let now = 0;
  let up = true;
  const v = createVerification({ env: env(), inner, now: () => now, fetchImpl: async () => { if (!up) throw new Error("down"); return ok(caps()); } });
  assert.equal((await v.ready()).ok, true);
  up = false;
  now += 61_000;
  assert.deepEqual(await v.ready(), { ok: false, rawCode: "kit_hs_unreachable" });
  up = true;
  assert.equal((await v.ready()).ok, true);
});

test("an incompatible service is kit_hs_mismatch with its KIT-HS code", async () => {
  const body = caps();
  body.ports.checks.named_policies = ["linear", "nonlinear"];
  const v = createVerification({ env: env(), inner, fetchImpl: async () => ok(body) });
  assert.deepEqual(await v.ready(), { ok: false, rawCode: "kit_hs_mismatch", code: "KIT-HS-006" });
});

test("the simulation switch is honoured only in local development: on a hosted environment it is a configuration problem", async () => {
  for (const APP_ENV of ["staging", "production", "preview"]) {
    for (const KIT_SIMULATION of ["1", "true", "0"]) {
      const hosted = { ...env({ APP_ENV, KIT_SIMULATION }), TRANSLATOR_BASE_URL: "https://checks.example.test" };
      assert.equal(createVerification({ env: hosted, inner }).configProblem(), "simulation_on_hosted", `${APP_ENV} ${KIT_SIMULATION}`);
    }
    assert.notEqual(workerEnvOf({ APP_ENV, KIT_SIMULATION: "1" }), "sim", APP_ENV);
  }
  assert.equal(workerEnvOf({ APP_ENV: "staging", KIT_SIMULATION: "1" }), "staging");
  assert.equal(workerEnvOf({ APP_ENV: "production", KIT_SIMULATION: "1" }), "production");
  // in local development the switch selects the simulation, as before
  assert.equal(workerEnvOf({ APP_ENV: "development", KIT_SIMULATION: "1" }), "sim");
  assert.equal(workerEnvOf({ KIT_SIMULATION: "1" }), "sim");
  assert.equal(createVerification({ env: env({ APP_ENV: "development" }), inner }).configProblem(), null);
  // even if the configuration check were skipped, a staging Worker with the switch set never accepts a sim service
  const sim = caps();
  const v = createVerification({ env: env({ APP_ENV: "staging", TRANSLATOR_BASE_URL: "https://checks.example.test" }), inner, fetchImpl: async () => ok(sim) });
  assert.equal(v.workerEnv, "staging");
  assert.equal((await v.ready()).code, "KIT-HS-009");
  assert.equal(evaluateCapabilities(sim, { workerEnv: v.workerEnv }).ok, false);
});

test("a hosted environment needs a live provider: a fixture service is refused on staging", async () => {
  const body = caps();
  body.service_env = "staging";
  const v = createVerification({ env: env({ KIT_SIMULATION: undefined, APP_ENV: "staging", TRANSLATOR_BASE_URL: "https://checks.example.test" }), inner,
    fetchImpl: async () => ok(body) });
  assert.equal((await v.ready()).code, "KIT-HS-009");
});

test("the router's absence changes nothing; an attached router is reported", async () => {
  const body = caps();
  body.ports.router.attached = true;
  body.ports.router.identity = { name: "test-flash-router", version: "0.1", rules_sha256: "a1".repeat(32), cost_data_sha256: "b2".repeat(32) };
  const v = createVerification({ env: env(), inner, fetchImpl: async () => ok(body) });
  const out = await v.ready();
  assert.equal(out.ok, true);
  assert.equal(out.router.identity.name, "test-flash-router");
});

test("only the kit's closed codes are stored as raw codes", () => {
  const v = createVerification({ env: env(), inner });
  assert.equal(v.rawCode({ kit: { rawCode: "kit_dl_010" } }), "kit_dl_010");
  assert.equal(v.rawCode({ kit: { rawCode: "anything_else" } }), undefined);
  assert.equal(v.rawCode({}), undefined);
});

test("turn.js's release gate releases only the exact text the verdict's deliverable names (condition 11)", async () => {
  // V3-L4: the gate turn.js calls re-checks the released text against the verdict, whatever produced the outcome, so a
  // result passed through unchanged with a verdict of its own cannot carry another text.
  const { verdict, context } = vector("verdict-binding", "deliver-bound");
  const v = createVerification({ env: env(), inner });
  const release = context.release_text;
  const result = { kind: "answer", requestId: "req-1", conversationId: "conv-1", turnVersion: 1, specialist: "history", text: release, references: [],
    review: "checks:integration.v1", checks: [], checksSummary: verdict.summary };
  // the checks of a ChatResult follow the verdict's material claims exactly
  const { checksFromVerdict } = await import("../src/verify/release-gate.js");
  Object.assign(result, checksFromVerdict(verdict));
  assert.equal(await v.releaseGate({ kit: { verdict } }, result), null);
  assert.deepEqual(await v.releaseGate({ kit: { verdict } }, { ...result, text: release + " An extra sentence." }), { rawCode: "kit_gate_binding" });
  assert.deepEqual(await v.releaseGate({ kit: { verdict } }, { ...result, text: undefined }), { rawCode: "kit_gate_binding" });
  const noDigest = structuredClone(verdict);
  delete noDigest.delivery.deliverable;
  assert.deepEqual(await v.releaseGate({ kit: { verdict: noDigest } }, result), { rawCode: "kit_gate_binding" });
  assert.deepEqual(await v.releaseGate({}, result), { rawCode: "kit_gate_binding" });
  const refused = { ...verdict, delivery: { ...verdict.delivery, decision: "refuse_incomplete" } };
  assert.deepEqual(await v.releaseGate({ kit: { verdict: refused } }, result), { rawCode: "kit_gate_decision" });
  assert.deepEqual(await v.releaseGate({ kit: { verdict } }, { ...result, review: "passed" }), { rawCode: "kit_gate_review" });
});
