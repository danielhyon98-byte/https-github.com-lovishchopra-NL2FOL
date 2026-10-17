// The specialist port of protocol epinoic.integration.v1: epinoic.integration.specialist-answer.v1 (PROTOCOL.md section 4).
//
// Invariants:
// - the runtime's frozen result is wrapped, never changed: `answer` is result.answer byte for byte, `log` is the
//   runtime's own redactForLog(result) without its `turn` and `usage` members (the conversation id never leaves the
//   Worker), `result_sha256` is the SHA-256 of the canonical JSON of the whole frozen result;
// - an envelope is built only for the outcome "answer" (which implies the runtime's gate passed); every other outcome
//   is refused with KIT-REQ-012 and maps to the base's own closed error without a checks call;
// - each result schema has its own accepted pair (result v1 with runtime v0.1.0, result v2 with runtime v0.2.0); an
//   unknown schema or contract is refused (KIT-REQ-010 / KIT-REQ-011), never coerced;
// - a gate pass is a format precondition, never evidence of verification;
// - the same projection and refusals as the service's specialist_port.envelope_for (integration/vectors/specialist-port/).

import { COMPATIBILITY } from "./compat.js";
import { CanonicalError } from "./canonical-json.js";
import { sha256Json, sha256Text, utf8Bytes } from "./sha256.js";

export const ENVELOPE_SCHEMA = "epinoic.integration.specialist-answer.v1";
export const PROTOCOL = "epinoic.integration.v1";
const STRIPPED_LOG_MEMBERS = Object.freeze(["turn", "usage"]);
const SELF_CERTIFICATION_KEYS = Object.freeze(["advisory_verification_status", "verified", "self_certified", "status"]);
const AGENT = /^(?:[a-z0-9]+(?:-[a-z0-9]+)*(?:@[ab])?|synthesis)$/;
const MAX_ANSWER_BYTES = COMPATIBILITY.limits.max_answer_bytes;

export const ACCEPTED_PAIRS = Object.freeze(Object.fromEntries(COMPATIBILITY.specialist_pairs.map((p) => [p.result, Object.freeze({ runtime: p.runtime, log: p.log })])));

/** A refusal of the specialist port, named by its closed KIT-REQ code. */
export class PortRefusal extends Error {
  constructor(code, detail) {
    super(`${code}: ${detail}`);
    this.name = "PortRefusal";
    this.code = code;
  }
}

/** The envelope's `log`: the runtime's redactForLog(result) without `turn` and `usage`. */
export function logProjection(redacted) {
  return Object.fromEntries(Object.entries(redacted).filter(([k]) => !STRIPPED_LOG_MEMBERS.includes(k)));
}

function refuse(code, detail) {
  throw new PortRefusal(code, detail);
}

/** The checks the service makes again, in the same order (shape, self-certification, schema and contract, log, outcome,
 * gate, provenance, size, digest, slug). Throws PortRefusal. */
export async function checkEnvelope(env, { slug = null } = {}) {
  if (env === null || typeof env !== "object" || Array.isArray(env)) refuse("KIT-REQ-001", "a specialist envelope must be a JSON object");
  const certifying = SELF_CERTIFICATION_KEYS.filter((k) => Object.hasOwn(env, k));
  if (certifying.length > 0) refuse("KIT-REQ-005", `self-certification field(s) at the envelope's top level: ${certifying.join(", ")}`);
  if (env.schema !== ENVELOPE_SCHEMA || env.protocol !== PROTOCOL) refuse("KIT-REQ-001", "not an epinoic.integration.specialist-answer.v1 envelope");
  const runtime = env.runtime;
  if (runtime === null || typeof runtime !== "object") refuse("KIT-REQ-001", "the envelope carries no runtime reference");
  const pair = Object.hasOwn(ACCEPTED_PAIRS, runtime.schema ?? "") ? ACCEPTED_PAIRS[runtime.schema] : null;
  if (pair === null) refuse("KIT-REQ-010", "the result schema is not an accepted specialist result schema");
  if (runtime.contract_version !== pair.runtime) refuse("KIT-REQ-011", "the runtime contract does not belong to the result schema");
  const log = env.log;
  if (log === null || typeof log !== "object" || Array.isArray(log)) refuse("KIT-REQ-001", "the envelope's log is not the runtime's log projection");
  if (log.schema !== pair.log || log.resultSchema !== runtime.schema) refuse("KIT-REQ-010", "the log projection is not the one of the result schema");
  if (log.contractVersion !== pair.runtime) refuse("KIT-REQ-011", "the log projection names another runtime contract");
  const stripped = STRIPPED_LOG_MEMBERS.filter((m) => Object.hasOwn(log, m));
  if (stripped.length > 0) refuse("KIT-REQ-001", `the log projection still carries ${stripped.join(", ")}, which never leave the Worker`);
  if (log.outcome !== "answer" || log.answerPresent !== true) refuse("KIT-REQ-012", "the specialist outcome is not an answer");
  if (log.gate === null || typeof log.gate !== "object" || log.gate.status !== "passed") refuse("KIT-REQ-013", "the specialist runtime's gate did not pass");
  const provenance = log.provenance;
  if (provenance === null || typeof provenance !== "object") refuse("KIT-REQ-001", "the log projection carries no provenance");
  if ((provenance.claims ?? null) !== null) refuse("KIT-REQ-011", "provenance.claims is not null: claims are extracted by the translator's parsers");
  if (typeof env.answer !== "string" || env.answer.length === 0) refuse("KIT-REQ-001", "the envelope carries no answer text");
  if (utf8Bytes(env.answer) > MAX_ANSWER_BYTES) refuse("KIT-REQ-006", `the answer exceeds ${MAX_ANSWER_BYTES} UTF-8 bytes`);
  if (typeof env.agent_id !== "string" || !AGENT.test(env.agent_id)) refuse("KIT-REQ-001", "the agent id is not a protocol agent id");
  let digest;
  try {
    digest = await sha256Text(env.answer);
  } catch {
    refuse("KIT-REQ-001", "the answer is not valid Unicode");
  }
  if (digest !== env.answer_sha256) refuse("KIT-REQ-014", "answer_sha256 is not the SHA-256 of the answer's UTF-8 bytes");
  if (slug !== null && provenance.slug !== slug) refuse("KIT-REQ-015", "the specialist's slug is not the subject map's slug for this task");
  return env;
}

/** The envelope of one frozen runtime result whose outcome is "answer". Throws PortRefusal for any other result. */
export async function envelopeFor(result, redacted, { agentId }) {
  const pair = Object.hasOwn(ACCEPTED_PAIRS, result?.schema ?? "") ? ACCEPTED_PAIRS[result.schema] : null;
  if (pair === null) refuse("KIT-REQ-010", "the result schema is not an accepted specialist result schema");
  if (result.contractVersion !== pair.runtime) refuse("KIT-REQ-011", "the runtime contract does not belong to the result schema");
  if (result.outcome !== "answer" || typeof result.answer !== "string") refuse("KIT-REQ-012", "the specialist outcome is not an answer");
  let resultSha256;
  try {
    resultSha256 = await sha256Json(result);
  } catch (err) {
    if (err instanceof CanonicalError) refuse("KIT-REQ-001", "the frozen result is not protocol JSON");
    throw err;
  }
  const env = {
    schema: ENVELOPE_SCHEMA,
    protocol: PROTOCOL,
    agent_id: agentId,
    runtime: { schema: result.schema, contract_version: result.contractVersion },
    log: logProjection(redacted),
    answer: result.answer,
    answer_sha256: await sha256Text(result.answer),
    result_sha256: resultSha256,
  };
  return checkEnvelope(env);
}
