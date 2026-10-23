// A2 (translator kit): the checks port's envelope over the repository's own offline runtime and synthetic bundle: an
// unchanged frozen result is wrapped, its digests agree with the cross-repository vectors, and every outcome other
// than an answer is refused. The non-answer turns use the copy's own callback vocabulary for its runtime contract
// (v0.1.0 in the harness, v0.2.0 in the retrained repository), and a sweep covers every outcome the copy's runtime
// declares. Run from the repository root: node --test integration/checks-port/test/*.test.js
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { OUTCOMES, RUNTIME_CONTRACT_VERSION } from "../../../specialist-runtime/src/constants.js";
import { redactForLog } from "../../../specialist-runtime/src/index.js";
import * as C from "../../../specialist-runtime/fixtures/synthetic/callbacks.js";
import * as H from "../../../specialist-runtime/fixtures/synthetic/harness.js";
import { PortRefusal, buildEnvelope, canonicalJson } from "../src/envelope.js";

const vectors = (name) => JSON.parse(readFileSync(new URL(`../vectors/${name}.json`, import.meta.url), "utf8"));
const refusedAsNotAnAnswer = (e) => e instanceof PortRefusal && e.code === "KIT-REQ-012";

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

test("the envelope agrees with the cross-repository vectors for the same runtime result", async () => {
  for (const name of ["v1-answer", "v2-answer"]) {
    const v = vectors(name);
    assert.deepEqual(await buildEnvelope(v.result, v.log, { agentId: v.agent_id }), v.expect.envelope, name);
  }
});

// The turns that end in another outcome than an answer, in each runtime contract's own callback vocabulary: v0.1.0's
// callback reports a finish reason; v0.2.0's returns the website's generation result (states complete, refused and
// incomplete) or a failure result, and a complete text without its sources line fails the gate.
const NOT_ANSWERS = {
  "epinoic.specialist-runtime.v0.1.0": () => [
    C.completedCallback({ text: H.GOOD_ANSWER, finishReason: "refusal" }),
    C.declinedCallback("budget_unavailable"),
    C.completedCallback({ text: H.GOOD_ANSWER, finishReason: "length" }),
  ],
  "epinoic.specialist-runtime.v0.2.0": () => [
    C.generationCallback(C.generationResult({ state: "refused", refusal: { category: null, beforeOutput: true } })),
    C.declinedCallback(),
    C.generationCallback(C.generationResult({ state: "incomplete", text: null, incompleteReason: "max_output_tokens" })),
    C.failedCallback(),
    C.completedCallback({ text: H.GOOD_ANSWER.split("\n").filter((line) => !line.startsWith("Sources:")).join("\n") }),
  ],
};

test("every other outcome is refused with KIT-REQ-012 and never wrapped", async () => {
  const cases = Object.hasOwn(NOT_ANSWERS, RUNTIME_CONTRACT_VERSION) ? NOT_ANSWERS[RUNTIME_CONTRACT_VERSION]() : null;
  assert.ok(cases, `runtime contract ${RUNTIME_CONTRACT_VERSION}: the checks port's tests know ${Object.keys(NOT_ANSWERS).join(" and ")} only`);
  for (const callback of cases) {
    const result = await run(callback);
    assert.notEqual(result.outcome, "answer");
    await assert.rejects(buildEnvelope(result, redactForLog(result), { agentId: "history" }), refusedAsNotAnAnswer);
  }
});

test("every outcome the runtime declares other than an answer is refused with KIT-REQ-012, whatever the other fields say", async () => {
  const genuine = await run(C.completedCallback({ text: H.GOOD_ANSWER }));
  assert.equal(genuine.outcome, "answer");
  const redacted = redactForLog(genuine);
  const others = OUTCOMES.filter((outcome) => outcome !== "answer");
  assert.ok(others.length > 0 && OUTCOMES.includes("answer"), "the runtime declares its closed set of outcomes");
  for (const outcome of others) {
    const forged = structuredClone(genuine);
    forged.outcome = outcome;
    await assert.rejects(buildEnvelope(forged, redacted, { agentId: "history" }), refusedAsNotAnAnswer, outcome);
  }
});
