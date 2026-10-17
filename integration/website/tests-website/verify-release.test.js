// Kit W4, the configuration pins (copied into the website's tests/ by integration/website/apply.mjs): the checks
// service is off in every block of wrangler.jsonc, the token is never a var, no CHAT_BACKEND value changed, and the
// verified backend needs owned state and a non-production environment. Z3 is not optional: a hosted environment can
// serve real specialist answers only through the verified backend.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { chatBackendMode } from "../src/chat/handler.js";
import { MODES, createVerification } from "../src/verify/verification.js";

const config = JSON.parse(readFileSync(new URL("../wrangler.jsonc", import.meta.url), "utf8").replace(/^\s*\/\/.*$/gm, ""));
const blocks = { production: config.vars, development: config.env.development.vars, staging: config.env.staging.vars };

test("every var block has the checks service off, and no block carries its token", () => {
  for (const [name, vars] of Object.entries(blocks)) {
    assert.equal(vars.TRANSLATOR_MODE, "none", name);
    assert.equal(vars.TRANSLATOR_BASE_URL, "", name);
    assert.ok(!Object.keys(vars).some((k) => /TRANSLATOR_SERVICE_TOKEN|TOKEN/i.test(k)), `${name}: the token is a secret, never a var`);
  }
  assert.deepEqual([blocks.production.CHAT_BACKEND, blocks.development.CHAT_BACKEND, blocks.staging.CHAT_BACKEND], ["none", "mock", "mock"]);
  assert.deepEqual(MODES, ["none", "http", "binding"]);
});

test("the verified backend needs owned state and runs only on loopback development or protected staging", () => {
  const local = new URL("http://127.0.0.1:8787/api/chat");
  assert.equal(chatBackendMode(local, { APP_ENV: "development", CHAT_BACKEND: "verified", CHAT_STATE: "d1" }), "verified");
  assert.equal(chatBackendMode(local, { APP_ENV: "development", CHAT_BACKEND: "verified", CHAT_STATE: "none" }), "none");
  const prod = new URL("https://epinoic.ai/api/chat");
  assert.equal(chatBackendMode(prod, { APP_ENV: "production", CHAT_BACKEND: "verified", CHAT_STATE: "d1" }), "none");
});

test("a URL that is not https outside loopback, or a missing mode, is a configuration problem", () => {
  const inner = { handle: async () => ({}) };
  const v = (env) => createVerification({ env: { TRANSLATOR_SERVICE_TOKEN: "kit-simulation-token-0123456789", ...env }, inner }).configProblem();
  assert.equal(v({ TRANSLATOR_MODE: "http", TRANSLATOR_BASE_URL: "http://checks.example.test" }), "translator_url");
  assert.equal(v({ TRANSLATOR_MODE: "none" }), "translator_mode");
  assert.equal(v({ TRANSLATOR_MODE: "http", TRANSLATOR_BASE_URL: "https://checks.example.test" }), null);
});
