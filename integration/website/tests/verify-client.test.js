// The outbound client of the checks service, with a fake fetchImpl (website/PATCH-PLAN.md, W2): every response becomes either
// strict protocol JSON or one closed failure code; nothing of a failing body is kept but a KIT-REQ code.
import assert from "node:assert/strict";
import test from "node:test";

import { baseUrlProblem, createConcurrencyLimit, createTranslatorClient, VERIFIER_FAILURES } from "../src/verify/translator-client.js";

const TOKEN = "kit-test-token-0123456789";
const json = (status, body, headers = {}) => new Response(typeof body === "string" ? body : JSON.stringify(body), {
  status, headers: { "Content-Type": "application/json", ...headers },
});
const client = (fetchImpl, extra = {}) => createTranslatorClient({ mode: "http", baseUrl: "https://checks.example.test", token: TOKEN, fetchImpl, limit: createConcurrencyLimit(4), ...extra });

test("a 200 strict JSON body is returned, with the bearer token and the protocol header sent", async () => {
  let seen;
  const r = await client(async (url, init) => {
    seen = { url, init };
    return json(200, { ok: 1 });
  }).capabilities();
  assert.deepEqual([r.ok, r.body], [true, { ok: 1 }]);
  assert.equal(seen.url, "https://checks.example.test/v1/capabilities");
  assert.equal(seen.init.headers.Authorization, `Bearer ${TOKEN}`);
  assert.equal(seen.init.headers["Epinoic-Protocol"], "integration.v1");
  assert.equal(seen.init.redirect, "manual");
});

for (const [status, code, headers] of [
  [302, "verifier_redirect", { Location: "https://elsewhere.test/" }], [401, "verifier_auth"], [403, "verifier_auth"],
  [429, "verifier_rate_limited", { "Retry-After": "99999" }], [503, "verifier_capacity"], [500, "verifier_error"], [418, "verifier_rejected"],
]) {
  test(`HTTP ${status} is the closed failure ${code}`, async () => {
    const r = await client(async () => json(status, { code: "E504", message: "x" }, headers ?? {})).checkTurn({}, { timeoutMs: 1000 });
    assert.equal(r.ok, false);
    assert.equal(r.code, code);
    assert.equal(r.retryable, VERIFIER_FAILURES[code]);
    if (status === 429) assert.equal(r.retryAfterSeconds, 3600);
  });
}

test("a 400 keeps only its KIT-REQ code", async () => {
  const r = await client(async () => json(400, { code: "KIT-REQ-015", message: "subject_unmapped", request_id: "x", extra: "student text" })).checkTurn({}, { timeoutMs: 1000 });
  assert.deepEqual([r.code, r.kitCode], ["verifier_rejected", "KIT-REQ-015"]);
  assert.ok(!JSON.stringify(r).includes("student text"));
});

test("a timeout, an abort and a network error are closed failures", async () => {
  const hang = (url, init) => new Promise((_resolve, reject) => init.signal.addEventListener("abort", () => reject(new Error("aborted"))));
  assert.equal((await client(hang).checkTurn({}, { timeoutMs: 20 })).code, "verifier_timeout");
  const ac = new AbortController();
  const pending = client(hang).checkTurn({}, { signal: ac.signal, timeoutMs: 5000 });
  ac.abort();
  assert.equal((await pending).code, "verifier_cancelled");
  assert.equal((await client(async () => { throw new Error("ECONNREFUSED"); }).checkTurn({}, { timeoutMs: 1000 })).code, "verifier_network");
  const aborted = new AbortController();
  aborted.abort();
  assert.equal((await client(hang).checkTurn({}, { signal: aborted.signal, timeoutMs: 1000 })).code, "verifier_cancelled");
});

test("an oversized, non-JSON, float-carrying or duplicate-key body is malformed", async () => {
  const big = "x".repeat(140000);
  assert.equal((await client(async () => json(200, `{"a":"${big}"}`)).checkTurn({}, { timeoutMs: 1000 })).code, "verifier_malformed");
  assert.equal((await client(async () => new Response("<html>", { status: 200, headers: { "Content-Type": "text/html" } })).checkTurn({}, { timeoutMs: 1000 })).code, "verifier_malformed");
  assert.equal((await client(async () => json(200, '{"a":1.5}')).checkTurn({}, { timeoutMs: 1000 })).code, "verifier_malformed");
  assert.equal((await client(async () => json(200, '{"a":1,"a":2}')).checkTurn({}, { timeoutMs: 1000 })).code, "verifier_malformed");
});

test("the isolate's concurrency limit answers busy without a request", async () => {
  const limit = createConcurrencyLimit(1);
  let calls = 0;
  const slow = () => new Promise((resolve) => setTimeout(() => { calls += 1; resolve(json(200, {})); }, 30));
  const c = client(slow, { limit });
  const first = c.checkTurn({}, { timeoutMs: 1000 });
  assert.equal((await c.checkTurn({}, { timeoutMs: 1000 })).code, "verifier_busy");
  assert.equal((await first).ok, true);
  assert.equal(calls, 1);
});

test("the base URL is https, or http on loopback only", () => {
  assert.equal(baseUrlProblem("https://checks.example.test"), null);
  assert.equal(baseUrlProblem("http://127.0.0.1:8899"), null);
  assert.equal(baseUrlProblem("http://checks.example.test"), "translator_url");
  assert.equal(baseUrlProblem("https://user:pw@checks.example.test"), "translator_url");
  assert.equal(baseUrlProblem("not a url"), "translator_url");
});

test("the binding transport calls the service binding, never fetch", async () => {
  let viaBinding = 0;
  const binding = { fetch: async () => { viaBinding += 1; return json(200, {}); } };
  const c = createTranslatorClient({ mode: "binding", binding, token: TOKEN, fetchImpl: () => assert.fail("fetch must not be called"), limit: createConcurrencyLimit(2) });
  assert.equal((await c.capabilities()).ok, true);
  assert.equal(viaBinding, 1);
});
