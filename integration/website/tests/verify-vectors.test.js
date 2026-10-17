// The cross-repository golden vectors, read by the Worker's adapter (PROTOCOL.md section 14.4): canonical JSON and digests, the
// handshake, the decision table, the verdict binding, the closed code table and the specialist port (v1 and v2) give
// exactly what the translator's service gives for the same inputs.
import assert from "node:assert/strict";
import test from "node:test";

import { CanonicalError, canonicalJson, parseStrict } from "../src/verify/canonical-json.js";
import { KIT_PUBLIC_CODES, publicCodeFor } from "../src/verify/codes.js";
import { POSITIVE, countClaims, decide, summarize } from "../src/verify/decision-table.js";
import { bindingProblem } from "../src/verify/release-gate.js";
import { sha256Json, sha256Text } from "../src/verify/sha256.js";
import { envelopeFor, PortRefusal } from "../src/verify/specialist-port.js";
import { evaluateCapabilities } from "../src/verify/verification.js";
import { vector, vectors } from "./kit-vectors.js";

test("canonical JSON and digests agree byte for byte with the translator", async () => {
  for (const v of vectors("canonical")) {
    if (v.name === "texts") {
      for (const t of v.texts) assert.equal(await sha256Text(t.text), t.sha256);
    } else if (v.name === "refused") {
      for (const doc of v.documents) assert.throws(() => parseStrict(doc), CanonicalError, doc);
    } else {
      assert.equal(canonicalJson(v.value), v.canonical, v.name);
      assert.equal(await sha256Json(v.value), v.sha256, v.name);
      assert.deepEqual(parseStrict(v.canonical), v.value, v.name);
    }
  }
});

test("a lone surrogate, a float and a repeated key are refused", () => {
  assert.throws(() => canonicalJson({ a: "\ud800" }), CanonicalError);
  assert.throws(() => canonicalJson({ a: 1.5 }), CanonicalError);
  assert.throws(() => parseStrict('{"a":1,"a":1}'), CanonicalError);
  assert.throws(() => parseStrict('{"a":{"b":1},"a":2}'), CanonicalError);
  assert.deepEqual(parseStrict('{"a":{"b":1},"c":{"b":2}}'), { a: { b: 1 }, c: { b: 2 } });
});

test("the handshake refuses the same capabilities with the same code", () => {
  const all = vectors("handshake");
  assert.ok(all.length >= 17);
  for (const v of all) {
    const out = evaluateCapabilities(v.capabilities, { workerEnv: v.worker_env, base: v.base });
    assert.deepEqual({ ok: out.ok, code: out.code, raw_code: out.rawCode }, v.expect, v.name);
  }
});

test("the decision table agrees with the service on every vector", () => {
  for (const v of vectors("decision-table")) {
    const f = v.fields;
    const inp = {
      policy: f.policy, revision_of: f.revision_of, receipt_status: f.receipt.status, receipt_error_codes: f.receipt.error_codes,
      overseer_state: f.overseer.state, delivery_allowed: f.overseer.delivery_allowed, overseer_refusal: f.overseer.refusal,
      consolidation_status: f.consolidation_status, blocking: f.counts.blocking, unavailable: f.counts.unavailable, claims: f.claims,
    };
    const [decision, reasons] = decide(inp);
    assert.deepEqual({ decision, reasons, summary: decision === "deliver" ? summarize(f.counts) : null }, v.expect, v.name);
    assert.deepEqual(countClaims(f.claims), f.counts, v.name);
  }
});

test("the verdict binding gives the service's outcome on every vector, the W-T cases included", async () => {
  const all = vectors("verdict-binding");
  for (let i = 1; i <= 8; i += 1) assert.ok(all.some((v) => v.name.startsWith(`W-T${i}-`)), `W-T${i}`);
  for (const v of all) {
    const c = v.context;
    const problem = await bindingProblem(v.verdict, {
      taskId: c.task_id, requestId: c.request_id, userText: c.user_text, policy: c.policy, mode: c.mode, answers: c.answers,
      releaseText: c.release_text, revisionOf: c.revision_of,
    });
    assert.deepEqual({ ok: problem === null, raw_code: problem ? problem[0] : null }, v.expect, v.name);
  }
});

test("the closed code table covers exactly the Worker's raw codes", () => {
  const { raw_codes: raws } = vector("codes", "worker-raw-codes");
  assert.deepEqual(Object.keys(KIT_PUBLIC_CODES).sort(), [...raws].sort());
  for (const raw of raws) {
    assert.match(raw, /^[a-z0-9_]{1,64}$/);
    assert.ok(["service_unavailable", "chat_unavailable", "review_unresolved", "checks_incomplete", "upstream_invalid"].includes(publicCodeFor(raw)), raw);
  }
  assert.equal(publicCodeFor("not_a_kit_code"), undefined);
  assert.equal(publicCodeFor("toString"), undefined);
});

test("the specialist port projects runtime results v1 and v2 exactly as the service does", async () => {
  for (const version of ["v1", "v2"]) {
    const all = vectors(`specialist-port/${version}`);
    assert.ok(all.some((v) => v.expect.envelope !== null), `${version} has an answer`);
    for (const v of all) {
      if (v.expect.envelope !== null) {
        assert.deepEqual(await envelopeFor(v.result, v.log, { agentId: v.agent_id }), v.expect.envelope, v.name);
      } else {
        await assert.rejects(envelopeFor(v.result, v.log, { agentId: v.agent_id }), (err) => err instanceof PortRefusal && err.code === v.expect.code, v.name);
      }
    }
  }
});

test("the chat-contract labels never claim truth or review", () => {
  const { labels, forbidden_words: forbidden } = vector("chat-contract", "labels");
  for (const text of Object.values(labels)) for (const word of forbidden) assert.ok(!new RegExp(`\\b${word}\\b`, "i").test(text), `${word} in ${text}`);
});

test("the answer badge says passed only when every material eligible claim has a permitted positive result", () => {
  const { badges, badge_cases: cases } = vector("chat-contract", "labels");
  const passed = ([text, tone]) => /passed/i.test(text) || tone === "is-ok";
  assert.deepEqual(Object.keys(badges).filter((s) => passed(badges[s])), ["formally_checked"]);
  for (const c of cases) {
    const summary = summarize(countClaims(c.claims));
    assert.equal(summary, c.summary, c.name);
    assert.deepEqual(badges[summary], c.badge, c.name);
  }
  // every list of up to three claims over the statuses a delivered answer can hold: a "passed" badge implies that every
  // material eligible claim is positive with its release permitted
  const kinds = [];
  for (const formal of ["ENTAILED", "CONSISTENT", "UNSUPPORTED", "INVALID_FORMALIZATION", "AMBIGUOUS_TRANSLATION", "UNKNOWN", "NOT_ELIGIBLE"]) {
    for (const permitted of [false, true]) {
      for (const materiality of ["material", "supporting"]) {
        kinds.push({ materiality, formal, attempt: formal === "NOT_ELIGIBLE" ? "not_eligible" : "attempted", release_permitted: permitted });
      }
    }
  }
  let lists = [[]];
  let seen = 0;
  for (let n = 1; n <= 3; n += 1) {
    lists = lists.flatMap((l) => kinds.map((k) => [...l, k]));
    for (const claims of lists) {
      seen += 1;
      if (!passed(badges[summarize(countClaims(claims))])) continue;
      const eligible = claims.filter((c) => c.materiality === "material" && c.attempt !== "not_eligible");
      assert.ok(eligible.length > 0 && eligible.every((c) => POSITIVE.includes(c.formal) && c.release_permitted), JSON.stringify(claims));
    }
  }
  assert.ok(seen > 20000);
});
