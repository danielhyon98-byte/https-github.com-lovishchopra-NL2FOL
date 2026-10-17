// The Worker's release gate for the verified backend (integration/PROTOCOL.md sections 8 and 9; PROTOCOL.md section 9, conditions 6 and 10 to 13).
//
// Invariants:
// - a verdict is accepted only when its shape is exactly epinoic.integration.turn-verdict.v1 (closed key sets, closed
//   enums, the pinned scope statements, a signature of the right algorithm): anything else is verifier_malformed;
// - it must be bound to this turn and attempt, this student text, this policy and mode and these answer digests, and
//   its decision, counts and summary must follow from its own fields (decision-table.js): anything else is kit_dl_030;
// - the text released is byte-identical to the checked deliverable (digest comparison), every listed excerpt is a
//   verbatim part of it, and the ChatResult says review "checks:integration.v1" with checks that agree with the verdict;
// - the Worker holds no verdict key (it cannot verify the HMAC); it checks that a signature is present.
// The same rules as the service's delivery.binding_problem, on the same vectors (integration/vectors/verdict-binding/).

import { compareCodePoints } from "./canonical-json.js";
import { countClaims, decide, decisionInputOf, summarize } from "./decision-table.js";
import { sha256Text, utf8Bytes } from "./sha256.js";

const freeze = Object.freeze;

export const SCOPE_STATEMENT =
  "This result concerns only the formal encoding it is bound to, under the encoded premises and the stated solver " +
  "configuration. It does not establish that the premises are factually true, that the natural-language claim was " +
  "translated faithfully, or that any interpretive judgement is correct. Grounding and semantic-fidelity information " +
  "is reported separately and is advisory.";
export const AUDIT_SCOPE_STATEMENT =
  "This audit covers only the transfers journaled since the auditor was attached to the channel. It shows whether the " +
  "recorded transfers, receipts and signed results agree with each other and with this repository's rules. It does " +
  "not show that any claim is true or any reading correct.";
export const VERIFIED_REVIEW = "checks:integration.v1";
export const CHECK_LIMITS = freeze({ maxChecks: 12, maxClaimChars: 200, maxResultBytes: 65536 });

// ------------------------------------------------------------------------------------------------- shape

const ID = /^[A-Za-z0-9._:-]{1,128}$/;
const SHA = /^[0-9a-f]{64}$/;
const TS = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/;
const AGENT = /^(?:[a-z0-9]+(?:-[a-z0-9]+)*(?:@[ab])?|synthesis)$/;
const VERSION = /^[0-9A-Za-z.+-]{1,40}$/;
const DL = /^KIT-DL-[0-9]{3}$/;
const RT = /^KIT-RT-[0-9]{3}$/;
const OVS = /^OVS-[A-Z]{2,12}-[0-9]{3}$/;
const FINDING = /^[A-Z][A-Z0-9]{0,15}(?:-[A-Z0-9]{1,16}){1,4}(?:\/[A-Z][A-Z0-9]{0,15}(?:-[A-Z0-9]{1,16}){1,4})?$/;
const ROLE = /^[a-z][a-z_]{0,63}$/;
const BASIS = /^[a-z][a-z0-9_]{0,63}$/;
const ROUTER_NAME = /^[a-z0-9][a-z0-9._-]{0,63}$/;
const ROUTER_VERSION = /^[0-9]{1,4}(?:\.[0-9]{1,4}){0,3}$/;
const FORMAL = freeze(["ENTAILED", "COUNTEREXAMPLE", "INCONSISTENT_PREMISES", "CONSISTENT", "SATISFIABLE", "UNSATISFIABLE", "UNKNOWN", "TIMEOUT",
  "UNSUPPORTED", "INVALID_FORMALIZATION", "AMBIGUOUS_TRANSLATION", "NOT_ELIGIBLE", "INTERNAL_ERROR", "NOT_ATTEMPTED"]);
const REFUSALS = freeze(["clearance_failed", "clearance_pending", "final_audit_not_passed", "signature_invalid", "custody_failed", "stale",
  "consolidation_conflicting", "no_deliverable_output", "receipt_error_findings", "not_deliverable", "internal_error"]);

const codePoints = (s) => [...s].length;
const str = (re, { min = 0, max = Infinity } = {}) => (v) => typeof v === "string" && (re === null || re.test(v)) && codePoints(v) >= min && codePoints(v) <= max;
const lit = (x) => (v) => v === x;
const oneOf = (...xs) => (v) => xs.includes(v);
const int = (min = 0) => (v) => Number.isSafeInteger(v) && v >= min;
const bool = (v) => v === true || v === false;
const list = (f, { min = 0, max = Infinity } = {}) => (v) => Array.isArray(v) && v.length >= min && v.length <= max && v.every(f);
const isPlain = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
/** A closed object: `required` keys must be present, `optional` keys may be absent (pydantic defaults), nothing else. */
const obj = (required, optional = {}) => (v) => {
  if (!isPlain(v)) return false;
  for (const k of Object.keys(v)) if (!Object.hasOwn(required, k) && !Object.hasOwn(optional, k)) return false;
  for (const [k, f] of Object.entries(required)) if (!Object.hasOwn(v, k) || !f(v[k])) return false;
  for (const [k, f] of Object.entries(optional)) if (Object.hasOwn(v, k) && !f(v[k])) return false;
  return true;
};
const orNull = (f) => (v) => v === null || f(v);

const routerIdentity = obj({ name: str(ROUTER_NAME), version: str(ROUTER_VERSION), rules_sha256: str(SHA), cost_data_sha256: str(SHA) });
const VERDICT = obj({
  schema: lit("epinoic.integration.turn-verdict.v1"),
  protocol: lit("epinoic.integration.v1"),
  verdict_id: str(ID),
  issued_at: str(TS),
  ids: obj({ task_id: str(ID), request_id: str(ID), plan_id: str(ID), channel_uid: str(ID) }),
  bound: obj({
    user_text_sha256: str(SHA), policy: oneOf("verified-v1", "verified-v1-qualify"), mode: oneOf("single", "duplicate", "combined"),
    answers: list(obj({ agent_id: str(AGENT, { max: 72 }), answer_sha256: str(SHA), result_sha256: str(SHA), report_id: str(ID), message_id: str(ID) }), { min: 1, max: 2 }),
  }),
  service: obj({
    service_env: oneOf("development", "staging", "production", "sim"),
    versions: obj({ ir: str(VERSION), engine: str(VERSION), policy: str(VERSION), translator: str(VERSION), z3: str(VERSION), contract: str(VERSION) }),
    build: obj({ build_id: str(SHA), schema_id: str(SHA), policy_id: str(SHA) }),
    subject_map_sha256: str(SHA),
  }),
  delivery: obj({ decision: oneOf("deliver", "revise", "refuse_unresolved", "refuse_incomplete", "refuse_integrity") }, {
    deliverable: orNull(obj({ agent_id: str(AGENT, { max: 72 }), answer_sha256: str(SHA), message_id: str(ID) })),
    reasons: list(str(DL), { max: 16 }),
    consolidation: orNull(obj({ id: str(ID), status: oneOf("CONSOLIDATED", "CONSOLIDATED_WITH_FINDINGS", "CONFLICTING", "NO_DELIVERABLE_OUTPUT"), basis: str(BASIS) })),
    synthesis: orNull(obj({ id: str(ID), receipt_status: oneOf("ACCEPTED", "ACCEPTED_WITH_FINDINGS", "REJECTED") })),
  }),
  overseer: obj({
    mode: oneOf("embedded", "sidecar"), final_audit_id: str(ID), state: oneOf("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS", "AUDIT_PENDING", "AUDIT_FAILED"),
    delivery_allowed: bool,
    review: obj({ queued: bool }, { plan_origin: orNull(oneOf("router", "floor")), plan_refusal: orNull(str(RT)), router: orNull(routerIdentity) }),
  }, { error_codes: list(str(OVS), { max: 64 }), refusal: orNull(oneOf(...REFUSALS)) }),
  receipt: obj({ status: oneOf("ACCEPTED", "ACCEPTED_WITH_FINDINGS", "REJECTED"), warning_count: int(0), branch: str(ROLE) },
    { error_codes: list(str(FINDING), { max: 128 }) }),
  counts: obj(Object.fromEntries(["claims_total", "material", "eligible", "attempted", "definitive", "positive", "permitted", "blocking", "unavailable", "not_eligible"].map((k) => [k, int(0)]))),
  scope_statement: lit(SCOPE_STATEMENT),
  audit_scope_statement: lit(AUDIT_SCOPE_STATEMENT),
  timings: obj({ total_ms: int(0), translation_ms: int(0), solver_ms: int(0), overseer_ms: int(0) }),
  signature: obj({ alg: lit("hmac-sha256"), key_id: str(ID), value: str(SHA) }),
}, {
  claims: list(obj({
    claim_id: str(ID), materiality: oneOf("material", "supporting"), role: str(ROLE), excerpt: str(null, { min: 1, max: 200 }),
    source: oneOf("translation", "branch_check", "stem"), formal: oneOf(...FORMAL),
    attempt: oneOf("attempted", "not_eligible", "skipped_cap", "skipped_budget", "provider_unavailable", "stem_budget"),
    fidelity: oneOf("faithful", "unfaithful", "uncertain", "missing", "stale", "unbound", "without_evidence"),
    evidence_resolved: bool, release_permitted: bool,
  }, { result_id: orNull(str(ID)), binding_digest: orNull(str(SHA)) }), { max: 32 }),
  summary: orNull(oneOf("formally_checked", "partly_checked", "formal_only", "not_formally_checkable", "incomplete")),
});

/** True when `verdict` has exactly the shape of epinoic.integration.turn-verdict.v1. */
export function isVerdictShape(verdict) {
  return VERDICT(verdict);
}

/** The verdict with the defaults of its optional members filled in (as the service's model reads it). */
function normalized(v) {
  return {
    ...v,
    delivery: { deliverable: null, reasons: [], consolidation: null, synthesis: null, ...v.delivery },
    overseer: { error_codes: [], refusal: null, ...v.overseer },
    receipt: { error_codes: [], ...v.receipt },
    claims: v.claims ?? [],
    summary: v.summary ?? null,
  };
}

const pairKey = (t) => t.join("\u0000");

/**
 * Row 1 of the decision table: null when `verdict` is well formed, bound to this attempt and internally consistent;
 * otherwise [rawCode, detail] with rawCode verifier_malformed or kit_dl_030.
 * `ctx`: { taskId, requestId, userText, policy, mode, answers: [[agentId, answerText, resultSha256]], releaseText, revisionOf }.
 */
export async function bindingProblem(verdict, ctx) {
  if (!isPlain(verdict)) return ["verifier_malformed", "not a JSON object"];
  if (!isVerdictShape(verdict)) return ["verifier_malformed", "not a turn verdict"];
  const v = normalized(verdict);
  if (v.ids.task_id !== ctx.taskId || v.ids.request_id !== ctx.requestId) return ["kit_dl_030", "ids differ from this turn and attempt"];
  let userDigest;
  try {
    userDigest = await sha256Text(ctx.userText);
  } catch {
    return ["kit_dl_030", "the user text has no digest"];
  }
  if (v.bound.user_text_sha256 !== userDigest) return ["kit_dl_030", "bound to another user text"];
  if (v.bound.policy !== ctx.policy || v.bound.mode !== ctx.mode) return ["kit_dl_030", "bound to another policy or mode"];
  const sent = [];
  for (const [agentId, text, resultSha] of ctx.answers) sent.push(pairKey([agentId, await sha256Text(text), resultSha]));
  const got = v.bound.answers.map((a) => pairKey([a.agent_id, a.answer_sha256, a.result_sha256]));
  if (JSON.stringify([...sent].sort(compareCodePoints)) !== JSON.stringify([...got].sort(compareCodePoints))) return ["kit_dl_030", "bound to other answers"];
  const [decision, reasons] = decide(decisionInputOf(v, ctx.revisionOf ?? null));
  const sortedReasons = [...v.delivery.reasons].sort();
  if (decision !== v.delivery.decision || JSON.stringify([...reasons].sort()) !== JSON.stringify(sortedReasons)) {
    return ["kit_dl_030", "the decision does not follow from the verdict's own fields"];
  }
  const listed = countClaims(v.claims.map((c) => ({ materiality: c.materiality, formal: c.formal, attempt: c.attempt, release_permitted: c.release_permitted })));
  if (v.counts.claims_total === v.claims.length && Object.keys(listed).some((k) => listed[k] !== v.counts[k])) return ["kit_dl_030", "the counts disagree with the listed claims"];
  if (decision === "deliver") {
    if (v.delivery.deliverable === null || typeof ctx.releaseText !== "string") return ["kit_dl_030", "a delivered verdict names its deliverable"];
    if (v.delivery.deliverable.answer_sha256 !== (await sha256Text(ctx.releaseText))) return ["kit_dl_030", "the text to release is not the checked deliverable"];
    if (v.summary !== summarize(v.counts)) return ["kit_dl_030", "the summary does not follow from the counts"];
    for (const c of v.claims) if (!ctx.releaseText.includes(c.excerpt)) return ["kit_dl_030", "a claim excerpt is not a verbatim part of the deliverable"];
  } else if (v.summary !== null) {
    return ["kit_dl_030", "only a delivered verdict carries a summary"];
  }
  return null;
}

// ------------------------------------------------------------------------------------------------- checks of a ChatResult

/** The ChatResult's `checks` (at most 12 material claims, in the verdict's order) and `checksSummary`. A positive
 * result is shown as faithful only when its fidelity is faithful, its evidence resolved and its release permitted;
 * otherwise a faithful translation reads "without_evidence": the page never over-claims. */
export function checksFromVerdict(verdict) {
  const v = normalized(verdict);
  const checks = v.claims
    .filter((c) => c.materiality === "material")
    .slice(0, CHECK_LIMITS.maxChecks)
    .map((c) => ({
      claim: c.excerpt,
      formal: c.formal,
      fidelity: c.fidelity === "faithful" && !(c.evidence_resolved && c.release_permitted) ? "without_evidence" : c.fidelity,
    }));
  return { checks, checksSummary: v.summary };
}

/**
 * The release gate turn.js calls after its own gate (PROTOCOL.md section 9, conditions 10 to 13): null, or { rawCode } with one of
 * the kit_gate_* codes. `verdict` already passed bindingProblem with this `result.text` as the release text.
 */
export function releaseGate(verdict, result) {
  if (!isPlain(result) || result.kind !== "answer") return { rawCode: "kit_gate_decision" };
  if (verdict?.delivery?.decision !== "deliver") return { rawCode: "kit_gate_decision" };
  if (result.review !== VERIFIED_REVIEW) return { rawCode: "kit_gate_review" };
  const expected = checksFromVerdict(verdict);
  if (JSON.stringify(result.checks) !== JSON.stringify(expected.checks) || result.checksSummary !== expected.checksSummary) return { rawCode: "kit_gate_checks" };
  if (utf8Bytes(JSON.stringify(result)) > CHECK_LIMITS.maxResultBytes) return { rawCode: "kit_gate_size" };
  return null;
}
