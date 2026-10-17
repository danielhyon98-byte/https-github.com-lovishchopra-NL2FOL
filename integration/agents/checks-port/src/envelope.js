// The specialist port of protocol epinoic.integration.v1, for the agents repository (A2; translator kit,
// integration/agents/PATCH-PLAN.md). The runtime's frozen result is wrapped, never changed; only the outcome "answer"
// has an envelope; claims stay null (they are extracted by the translator's branch parsers).
//
// Portability: only globalThis.crypto.subtle and TextEncoder are used (the repository's check:portable rule).
// The digests and the projection are the same as the website's (integration/website/src/verify/specialist-port.js)
// and the service's (specialist_port.envelope_for), on the same vectors (integration/vectors/specialist-port/).

export const ENVELOPE_SCHEMA = "epinoic.integration.specialist-answer.v1";
export const PROTOCOL = "epinoic.integration.v1";
export const ACCEPTED_PAIRS = Object.freeze({
  "epinoic.specialist-turn-result.v1": Object.freeze({ runtime: "epinoic.specialist-runtime.v0.1.0", log: "epinoic.specialist-turn-log.v1" }),
  "epinoic.specialist-turn-result.v2": Object.freeze({ runtime: "epinoic.specialist-runtime.v0.2.0", log: "epinoic.specialist-turn-log.v2" }),
});
const STRIPPED = Object.freeze(["turn", "usage"]);
const ENCODER = new TextEncoder();

export class PortRefusal extends Error {
  constructor(code, detail) {
    super(`${code}: ${detail}`);
    this.name = "PortRefusal";
    this.code = code;
  }
}

function compareCodePoints(a, b) {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i += 1) {
    let x = a.charCodeAt(i);
    let y = b.charCodeAt(i);
    if (x === y) continue;
    if (x >= 0xd800) x = x >= 0xe000 ? x - 0x800 : x + 0x2000;
    if (y >= 0xd800) y = y >= 0xe000 ? y - 0x800 : y + 0x2000;
    return x - y;
  }
  return a.length - b.length;
}

function hasLoneSurrogate(text) {
  for (let i = 0; i < text.length; i += 1) {
    const c = text.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff) {
      const d = text.charCodeAt(i + 1);
      if (d >= 0xdc00 && d <= 0xdfff) { i += 1; continue; }
      return true;
    }
    if (c >= 0xdc00 && c <= 0xdfff) return true;
  }
  return false;
}

/** Canonical JSON of protocol epinoic.integration.v1 (keys by code point, integers only, no lone surrogate). */
export function canonicalJson(value) {
  if (value === null || value === true || value === false) return JSON.stringify(value);
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) throw new PortRefusal("KIT-REQ-001", "a number that is not a safe integer");
    return JSON.stringify(value);
  }
  if (typeof value === "string") {
    if (hasLoneSurrogate(value)) throw new PortRefusal("KIT-REQ-001", "a lone surrogate");
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (typeof value === "object") {
    const keys = Object.keys(value).sort(compareCodePoints);
    return `{${keys.map((k) => `${canonicalJson(k)}:${canonicalJson(value[k])}`).join(",")}}`;
  }
  throw new PortRefusal("KIT-REQ-001", `a value of type ${typeof value}`);
}

async function sha256Hex(text) {
  const digest = await globalThis.crypto.subtle.digest("SHA-256", ENCODER.encode(text));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** The envelope of one frozen result whose outcome is "answer"; `redacted` is the runtime's redactForLog(result). */
export async function buildEnvelope(result, redacted, { agentId }) {
  const pair = Object.hasOwn(ACCEPTED_PAIRS, result?.schema ?? "") ? ACCEPTED_PAIRS[result.schema] : null;
  if (pair === null) throw new PortRefusal("KIT-REQ-010", "the result schema is not an accepted specialist result schema");
  if (result.contractVersion !== pair.runtime) throw new PortRefusal("KIT-REQ-011", "the runtime contract does not belong to the result schema");
  if (result.outcome !== "answer" || typeof result.answer !== "string") throw new PortRefusal("KIT-REQ-012", "the specialist outcome is not an answer");
  if ((redacted?.provenance?.claims ?? null) !== null) throw new PortRefusal("KIT-REQ-011", "provenance.claims is not null");
  if (redacted?.gate?.status !== "passed") throw new PortRefusal("KIT-REQ-013", "the runtime's gate did not pass");
  if (hasLoneSurrogate(result.answer)) throw new PortRefusal("KIT-REQ-001", "the answer is not valid Unicode");
  return {
    schema: ENVELOPE_SCHEMA,
    protocol: PROTOCOL,
    agent_id: agentId,
    runtime: { schema: result.schema, contract_version: result.contractVersion },
    log: Object.fromEntries(Object.entries(redacted).filter(([k]) => !STRIPPED.includes(k))),
    answer: result.answer,
    answer_sha256: await sha256Hex(result.answer),
    result_sha256: await sha256Hex(canonicalJson(result)),
  };
}
