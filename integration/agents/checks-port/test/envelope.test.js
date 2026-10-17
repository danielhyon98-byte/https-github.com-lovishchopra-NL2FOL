// A2 (translator kit): the checks port's envelope over the repository's own offline runtime and synthetic bundle: an
// unchanged frozen result is wrapped, its digests agree with the cross-repository vectors, and every outcome other
// than an answer is refused. Run from the repository root: node --test integration/checks-port/test/*.test.js
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { redactForLog } from "../../../specialist-runtime/src/index.js";
import * as C from "../../../specialist-runtime/fixtures/synthetic/callbacks.js";
import * as H from "../../../specialist-runtime/fixtures/synthetic/harness.js";
import { PortRefusal, buildEnvelope, canonicalJson } from "../src/envelope.js";

const vectors = (name) => JSON.parse(readFileSync(new URL(`../vectors/${name}.json`, import.meta.url), "utf8"));

async function run(callback) {
  const rt = H.offlineRuntime();
  const bundle = await H.loadSyntheticBundle(rt);
  return rt.runSpecialistTurn(H.turnInput(bundle, callback.authorizedGenerate));
}

test("an answer is wrapped unchanged, with claims null and the gate passed", async () => {
  const result = await run(C.completedCallback({ text: H.GOOD_ANSWER }));
  const before = canonicalJson(result);
  const env = await buildEnvelope(result, redactForLog(result), { agentId: "history" });
  assert.equal(canonicalJson(result), before, "the frozen result is never changed");
  assert.equal(env.answer, result.answer);
  assert.equal(env.log.provenance.claims, null);
  assert.ok(!("turn" in env.log) && !("usage" in env.log));
  assert.match(env.answer_sha256, /^[0-9a-f]{64}$/);
});

test("the envelope agrees with the cross-repository vector for the same runtime result", async () => {
  const v = vectors("v1-answer");
  assert.deepEqual(await buildEnvelope(v.result, v.log, { agentId: v.agent_id }), v.expect.envelope);
});

test("every other outcome is refused with KIT-REQ-012 and never wrapped", async () => {
  for (const callback of [C.completedCallback({ text: H.GOOD_ANSWER, finishReason: "refusal" }), C.declinedCallback("budget_unavailable"),
    C.completedCallback({ text: H.GOOD_ANSWER, finishReason: "length" })]) {
    const result = await run(callback);
    assert.notEqual(result.outcome, "answer");
    await assert.rejects(buildEnvelope(result, redactForLog(result), { agentId: "history" }), (e) => e instanceof PortRefusal && e.code === "KIT-REQ-012");
  }
});
