// The closed raw-to-public code table of protocol epinoic.integration.v1 (integration/PROTOCOL.md section 8).
//
// Invariants:
// - every raw code the verified backend stores in D1 is a key here, and nothing else is (tests/verify-vectors.test.js
//   compares the keys with integration/vectors/codes/worker-raw-codes.json, the translator's WORKER_RAW_CODES);
// - every raw code matches ^[a-z0-9_]{1,64}$ and maps to exactly one public code the website already answers with or
//   that W1 adds (review_unresolved, checks_incomplete);
// - history shows the same public code that POST answered: publicTurnCode looks a stored code up here first;
// - after the specialist call has been sent, every refusal is final (no public code here is retryable except
//   service_unavailable, which is reached only before any paid call).

const freeze = Object.freeze;

const SERVICE_UNAVAILABLE = ["kit_hs_not_ready", "kit_hs_unreachable", "kit_hs_mismatch"];
const CHAT_UNAVAILABLE = ["specialist_unmapped", "specialist_unavailable"];
const SPECIALIST_OUTCOMES = [
  "specialist_precondition_failed", "specialist_declined", "specialist_failed", "specialist_refusal", "specialist_refused",
  "specialist_incomplete", "specialist_oversize", "specialist_gate_failed", "specialist_gate_unverifiable",
];
const CHECKS_CALL_FAILED = [
  "verifier_busy", "verifier_cancelled", "verifier_timeout", "verifier_network", "verifier_redirect", "verifier_auth",
  "verifier_rate_limited", "verifier_capacity", "verifier_rejected", "verifier_error",
];
const UNRESOLVED = ["kit_dl_002", "kit_dl_007", "kit_dl_008", "kit_dl_010", "kit_dl_012", "kit_dl_020"];
const INCOMPLETE = ["kit_dl_004", "kit_dl_011", "kit_dl_013", "kit_dl_900"];
const INTEGRITY = [
  "kit_dl_001", "kit_dl_003", "kit_dl_005", "kit_dl_006", "kit_dl_030", "verifier_malformed", "verifier_binding_mismatch",
  "kit_gate_binding", "kit_gate_decision", "kit_gate_review", "kit_gate_checks", "kit_gate_raw_body", "kit_gate_size",
];

function table(groups) {
  const out = {};
  for (const [publicCode, raws] of groups) for (const raw of raws) out[raw] = publicCode;
  return freeze(out);
}

/** raw code -> public code (integration/PROTOCOL.md section 8). */
export const KIT_PUBLIC_CODES = table([
  ["service_unavailable", SERVICE_UNAVAILABLE],
  ["chat_unavailable", CHAT_UNAVAILABLE],
  ["review_unresolved", SPECIALIST_OUTCOMES],
  ["checks_incomplete", CHECKS_CALL_FAILED],
  ["review_unresolved", UNRESOLVED],
  ["checks_incomplete", INCOMPLETE],
  ["upstream_invalid", INTEGRITY],
]);

/** The public codes the table answers with, and the HTTP status and retryability W1 gives the two new ones. */
export const KIT_NEW_ERRORS = freeze({
  review_unresolved: freeze({ status: 422, retryable: false }),
  checks_incomplete: freeze({ status: 503, retryable: false }),
});

const RAW = /^[a-z0-9_]{1,64}$/;

/** The public code of a stored raw code, or undefined for a code this table does not own. */
export function publicCodeFor(raw) {
  return typeof raw === "string" && RAW.test(raw) && Object.hasOwn(KIT_PUBLIC_CODES, raw) ? KIT_PUBLIC_CODES[raw] : undefined;
}

/** The raw code a delivery reason (KIT-DL-0xx) is stored under. */
export function rawCodeForReason(reason) {
  const m = /^KIT-DL-([0-9]{3})$/.exec(reason ?? "");
  const raw = m ? `kit_dl_${m[1]}` : undefined;
  return raw !== undefined && Object.hasOwn(KIT_PUBLIC_CODES, raw) ? raw : undefined;
}

/** Only codes this table owns may be stored by the verified backend (turn.js stores rawCode(outcome) ?? result.code). */
export function isKitRawCode(raw) {
  return publicCodeFor(raw) !== undefined;
}
