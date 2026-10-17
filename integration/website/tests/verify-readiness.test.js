// The verified backend's readiness (PROTOCOL.md section 3, checks 3 and 4; website/PATCH-PLAN.md, W2): the configuration check is synchronous, the
// handshake is cached for 60 s by an injected clock, a stale cache refreshes once, and a refresh failure leaves the
// backend not ready. The flash router is reported, never required.
import assert from "node:assert/strict";
import test from "node:test";

import { createVerification } from "../src/verify/verification.js";
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
