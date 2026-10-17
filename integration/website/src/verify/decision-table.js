// The decision table of protocol epinoic.integration.v1, re-derived in the Worker (integration/PROTOCOL.md section 8).
//
// Invariants:
// - the same function of the same verdict fields as the service's delivery.decide (golden vectors in
//   integration/vectors/decision-table/, run by tests/verify-vectors.test.js on both sides);
// - rows in order, first match wins; only material claims count where a row says so;
// - a verdict the service issued after an unexpected exception (refusal internal_error) is refuse_incomplete
//   (KIT-DL-900) before every row: it never delivers;
// - an answer whose required checks did not complete is never summarised as formally_checked, whatever the policy.

const freeze = Object.freeze;

export const DEFINITIVE = freeze(["ENTAILED", "COUNTEREXAMPLE", "INCONSISTENT_PREMISES", "CONSISTENT", "SATISFIABLE", "UNSATISFIABLE"]);
export const POSITIVE = freeze(["ENTAILED", "CONSISTENT", "SATISFIABLE"]);
export const NEGATIVE = freeze(["COUNTEREXAMPLE", "INCONSISTENT_PREMISES", "UNSATISFIABLE"]);
export const INCOMPLETE_STATUSES = freeze(["UNKNOWN", "TIMEOUT", "INTERNAL_ERROR", "NOT_ATTEMPTED"]);
const BUDGET_ATTEMPTS = freeze(["skipped_budget", "stem_budget"]);
/** No v1 policy allows a revision (decision D5): "revise" is never produced. */
export const REVISION_POLICIES = freeze([]);
const INTEGRITY_REFUSALS = freeze({
  clearance_failed: "KIT-DL-003", final_audit_not_passed: "KIT-DL-005", signature_invalid: "KIT-DL-006",
  custody_failed: "KIT-DL-006", stale: "KIT-DL-006", not_deliverable: "KIT-DL-006",
});
const UNRESOLVED_REFUSALS = freeze({
  receipt_error_findings: "KIT-DL-002", consolidation_conflicting: "KIT-DL-007", no_deliverable_output: "KIT-DL-008",
});

const material = (c) => c.materiality === "material";
const eligible = (c) => c.attempt !== "not_eligible";
const uniqueSorted = (xs) => [...new Set(xs)].sort();

/** The verdict's counts over every claim (only claims_total counts supporting claims). */
export function countClaims(claims) {
  const m = claims.filter(material);
  const e = m.filter(eligible);
  return {
    claims_total: claims.length,
    material: m.length,
    eligible: e.length,
    attempted: e.filter((c) => c.attempt === "attempted").length,
    definitive: e.filter((c) => DEFINITIVE.includes(c.formal)).length,
    positive: e.filter((c) => POSITIVE.includes(c.formal)).length,
    permitted: e.filter((c) => POSITIVE.includes(c.formal) && c.release_permitted === true).length,
    blocking: m.filter((c) => NEGATIVE.includes(c.formal)).length,
    unavailable: e.filter((c) => INCOMPLETE_STATUSES.includes(c.formal)).length,
    not_eligible: m.filter((c) => !eligible(c)).length,
  };
}

/** Rows 2 to 7: [decision, reasons]. Row 1 is the binding check (release-gate.js). */
export function decide(inp) {
  if (inp.overseer_refusal === "internal_error") return ["refuse_incomplete", ["KIT-DL-900"]];
  const reasons = [];
  if (inp.receipt_status === "REJECTED") reasons.push("KIT-DL-001");
  if (inp.overseer_state === "AUDIT_FAILED") reasons.push("KIT-DL-005");
  if (Object.hasOwn(INTEGRITY_REFUSALS, inp.overseer_refusal ?? "")) reasons.push(INTEGRITY_REFUSALS[inp.overseer_refusal]);
  if (!inp.delivery_allowed && (inp.overseer_refusal ?? null) === null && inp.overseer_state !== "AUDIT_PENDING") reasons.push("KIT-DL-006");
  if (reasons.length > 0) return ["refuse_integrity", uniqueSorted(reasons)];
  if (inp.overseer_state === "AUDIT_PENDING" || inp.overseer_refusal === "clearance_pending") return ["refuse_incomplete", ["KIT-DL-004"]];
  if (inp.receipt_error_codes.length > 0) reasons.push("KIT-DL-002");
  if (Object.hasOwn(UNRESOLVED_REFUSALS, inp.overseer_refusal ?? "")) reasons.push(UNRESOLVED_REFUSALS[inp.overseer_refusal]);
  if (inp.consolidation_status === "CONFLICTING") reasons.push("KIT-DL-007");
  if (inp.consolidation_status === "NO_DELIVERABLE_OUTPUT") reasons.push("KIT-DL-008");
  if (inp.blocking > 0) reasons.push("KIT-DL-010");
  if (reasons.length > 0) {
    if (REVISION_POLICIES.includes(inp.policy) && inp.revision_of === null) return ["revise", uniqueSorted(reasons)];
    if (inp.revision_of !== null) reasons.push("KIT-DL-020");
    return ["refuse_unresolved", uniqueSorted(reasons)];
  }
  if (!inp.delivery_allowed) return ["refuse_integrity", ["KIT-DL-006"]];
  if (inp.unavailable > 0 && inp.policy === "verified-v1") {
    const out = ["KIT-DL-011"];
    if (inp.claims.some((c) => material(c) && eligible(c) && INCOMPLETE_STATUSES.includes(c.formal) && BUDGET_ATTEMPTS.includes(c.attempt))) out.push("KIT-DL-013");
    return ["refuse_incomplete", out];
  }
  return ["deliver", []];
}

/** The summary of a delivered answer, from its counts. */
export function summarize(counts) {
  if (counts.unavailable > 0) return "incomplete";
  if (counts.positive === 0) return "not_formally_checkable";
  if (counts.permitted === counts.eligible) return "formally_checked";
  if (counts.permitted > 0) return "partly_checked";
  return "formal_only";
}

/** The decision-table input read from a verdict (the same fields the service reads). */
export function decisionInputOf(verdict, revisionOf = null) {
  const consolidation = verdict.delivery.consolidation;
  return {
    policy: verdict.bound.policy,
    revision_of: revisionOf,
    receipt_status: verdict.receipt.status,
    receipt_error_codes: [...verdict.receipt.error_codes],
    overseer_state: verdict.overseer.state,
    delivery_allowed: verdict.overseer.delivery_allowed === true,
    overseer_refusal: verdict.overseer.refusal ?? null,
    consolidation_status: consolidation ? consolidation.status : null,
    blocking: verdict.counts.blocking,
    unavailable: verdict.counts.unavailable,
    claims: verdict.claims.map((c) => ({ materiality: c.materiality, formal: c.formal, attempt: c.attempt, release_permitted: c.release_permitted === true })),
  };
}
