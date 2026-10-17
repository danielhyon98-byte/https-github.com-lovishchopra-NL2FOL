// Kit W1, the contract reader (copied into the website's tests/ by integration/website/apply.mjs): a verified answer's
// checks validate through chatResultProblem and through history's replyProblem; old rows without checks still replay;
// every malformed check is refused; the labels are the closed copy; the two new codes are final.
import assert from "node:assert/strict";
import test from "node:test";

import {
  CHECK_BADGES, CHECK_LIMITS, CHECK_SUMMARIES, REVIEW_STATES, SCOPE_STATEMENT, VERIFIED_REVIEW, chatResultProblem, checkLabel, checksBadge,
  conversationProblem,
} from "../public/chat-contract.js";
import { ERROR_CODES, errorResult, statusForError } from "../src/chat/contract.js";
import { KIT_PUBLIC_CODES } from "../src/verify/codes.js";
import { vector } from "./kit-vectors.js";

const answer = (extra = {}) => ({
  kind: "answer", requestId: "req-1", conversationId: "conv_00000001", turnVersion: 1, specialist: "history",
  text: "The Treaty of Versailles (1919) imposed reparations.", references: [], review: VERIFIED_REVIEW,
  checks: [{ claim: "The Treaty of Versailles (1919) imposed reparations.", formal: "ENTAILED", fidelity: "without_evidence" }],
  checksSummary: "formal_only", ...extra,
});

test("the review states are append-only and name the verified review last", () => {
  assert.deepEqual(REVIEW_STATES.slice(0, 2), ["passed", "not_required"]);
  assert.equal(REVIEW_STATES.at(-1), "checks:integration.v1");
});

test("a verified answer with its checks validates, and an old answer without checks still does", () => {
  assert.equal(chatResultProblem(answer(), 200), null);
  const old = answer({ review: "passed" });
  delete old.checks;
  delete old.checksSummary;
  assert.equal(chatResultProblem(old, 200), null);
});

for (const [name, change] of [
  ["an unknown status", { checks: [{ claim: "x", formal: "VERIFIED", fidelity: "missing" }] }],
  ["a negative status on a delivered answer", { checks: [{ claim: "x", formal: "COUNTEREXAMPLE", fidelity: "missing" }] }],
  ["an extra key in an entry", { checks: [{ claim: "x", formal: "ENTAILED", fidelity: "missing", verified: true }] }],
  ["an unknown fidelity", { checks: [{ claim: "x", formal: "ENTAILED", fidelity: "proven" }] }],
  ["more than 12 entries", { checks: Array.from({ length: CHECK_LIMITS.maxChecks + 1 }, () => ({ claim: "x", formal: "ENTAILED", fidelity: "missing" })) }],
  ["a claim over 200 characters", { checks: [{ claim: "x".repeat(201), formal: "ENTAILED", fidelity: "missing" }] }],
  ["an unknown summary", { checksSummary: "verified" }],
  ["checks under review passed", { review: "passed" }],
  ["checks under review not_required", { review: "not_required" }],
]) {
  test(`a verified answer with ${name} is refused`, () => {
    assert.equal(chatResultProblem(answer(change), 200), "checks");
  });
}

test("only one of the two fields, or the verified review without checks, is refused", () => {
  const onlyChecks = answer();
  delete onlyChecks.checksSummary;
  assert.equal(chatResultProblem(onlyChecks, 200), "checks");
  const onlySummary = answer();
  delete onlySummary.checks;
  assert.equal(chatResultProblem(onlySummary, 200), "checks");
  const bare = answer();
  delete bare.checks;
  delete bare.checksSummary;
  assert.equal(chatResultProblem(bare, 200), "checks");
});

test("history validates a stored verified reply's checks instead of dropping them", () => {
  const time = "2026-10-17T00:00:00.000Z";
  const turn = (reply) => ({ clientTurnId: "turn_00000001", message: "q", askedAt: time, status: "answered", turnVersion: 1, answeredAt: time,
    reply, errorCode: null, attemptRef: null, attempts: 1, simulated: true, routing: "mock" });
  const body = (reply) => ({ ok: true, earlier: null,
    conversation: { id: "conv_00000001", title: "t", subject: "history", turnVersion: 1, status: "idle", createdAt: time, updatedAt: time },
    turns: [turn(reply)] });
  const reply = { kind: "answer", specialist: "history", text: "a", references: [], review: VERIFIED_REVIEW,
    checks: [{ claim: "a", formal: "ENTAILED", fidelity: "missing" }], checksSummary: "formal_only" };
  assert.equal(conversationProblem(body(reply)), null);
  assert.equal(conversationProblem(body({ ...reply, checks: [{ claim: "a", formal: "BOGUS", fidelity: "missing" }] })), "reply_content");
  const old = { kind: "answer", specialist: "history", text: "a", references: [], review: "passed" };
  assert.equal(conversationProblem(body(old)), null);
});

test("the labels are the closed copy and never claim truth or review", () => {
  const { labels, forbidden_words: forbidden } = vector("chat-contract", "labels");
  assert.equal(checkLabel({ formal: "ENTAILED", fidelity: "faithful" }), labels.positive_faithful_resolved);
  assert.equal(checkLabel({ formal: "CONSISTENT", fidelity: "without_evidence" }), labels.positive_other);
  for (const status of ["NOT_ELIGIBLE", "UNSUPPORTED", "INVALID_FORMALIZATION", "AMBIGUOUS_TRANSLATION", "UNKNOWN", "TIMEOUT", "INTERNAL_ERROR", "NOT_ATTEMPTED"]) {
    assert.equal(checkLabel({ formal: status, fidelity: "missing" }), labels[status], status);
  }
  for (const text of Object.values(labels)) for (const w of forbidden) assert.ok(!new RegExp(`\\b${w}\\b`, "i").test(text), text);
});

test("the answer badge follows the checks summary: passed only with a positive result and no missing material check", () => {
  const { badges, unknown_summary_badge: unknown, forbidden_words: forbidden } = vector("chat-contract", "labels");
  assert.deepEqual(Object.keys(CHECK_BADGES).sort(), [...CHECK_SUMMARIES].sort());
  assert.deepEqual(Object.keys(badges).sort(), [...CHECK_SUMMARIES].sort());
  for (const summary of CHECK_SUMMARIES) {
    assert.deepEqual(checksBadge(summary), badges[summary], summary);
    assert.deepEqual(checksBadge(summary, " (simulated)"), [`${badges[summary][0]} (simulated)`, badges[summary][1]], summary);
  }
  for (const summary of ["not_formally_checkable", "incomplete"]) {
    const [text, tone] = checksBadge(summary);
    assert.doesNotMatch(text, /passed|checked:/i, summary);
    assert.equal(tone, null, summary);
  }
  for (const summary of ["formally_checked", "partly_checked", "formal_only"]) assert.equal(checksBadge(summary)[0], "Automatic checks passed", summary);
  for (const odd of [undefined, null, "", "verified", "toString", "__proto__"]) assert.deepEqual(checksBadge(odd), unknown, String(odd));
  for (const [text] of [...Object.values(badges), unknown]) for (const w of forbidden) assert.ok(!new RegExp(`\\b${w}\\b`, "i").test(text), text);
});

test("the scope statement is the engine's, verbatim", () => {
  assert.equal(SCOPE_STATEMENT, vector("verdict-binding", "deliver-bound").verdict.scope_statement);
});

test("the two new public codes are final, and every kit raw code maps to a public code POST can answer", () => {
  assert.deepEqual([statusForError("review_unresolved"), errorResult("r", "review_unresolved").retryable], [422, false]);
  assert.deepEqual([statusForError("checks_incomplete"), errorResult("r", "checks_incomplete").retryable], [503, false]);
  for (const [raw, pub] of Object.entries(KIT_PUBLIC_CODES)) assert.ok(ERROR_CODES.includes(pub), `${raw} -> ${pub}`);
});
