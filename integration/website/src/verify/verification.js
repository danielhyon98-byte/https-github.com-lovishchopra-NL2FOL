// Readiness of the verified backend (protocol epinoic.integration.v1; PROTOCOL.md section 3, checks 3 and 4).
//
// Invariants:
// - configProblem() is synchronous and runs before admission: an incomplete configuration answers 503
//   chat_unavailable with nothing stored or charged, and is logged only as the label kit_config:<problem>;
// - the simulation switch KIT_SIMULATION is honoured only in local development: set on staging, production or any
//   other APP_ENV it is the configuration problem simulation_on_hosted, and it never makes a hosted Worker accept a
//   simulation service (workerEnvOf);
// - ready({ signal }) runs after admission and before routing: it needs a capabilities response fetched less than
//   60 s ago by this object (one GET, 3 s timeout, injectable now()) that matches the pinned compatibility set and
//   reports a passed self-test; otherwise the attempt fails with kit_hs_not_ready, kit_hs_unreachable or
//   kit_hs_mismatch, and no classifier, specialist or checks call is made; a replay never reaches it. The handler
//   creates one object per request, so every turn that is not a replay fetches the capabilities once (measured in the
//   simulation); a cache shared across requests is an optimisation, recorded and not built;
// - evaluateCapabilities() states the same rules as the service's handshake.evaluate on the same golden vectors
//   (integration/vectors/handshake/), so both sides refuse the same responses with the same KIT-HS code;
// - the flash router is reported, never required: its absence changes nothing here, and an incoherent report of it
//   (attached without an identity, an identity while detached, a refusal while attached, a refusal no attachment gives,
//   a router named by the floor's reserved identity) is out of contract, KIT-HS-001, as in the service's
//   protocol.RouterPortCaps;
// - Z3 is not optional: there is no mode in which an answer is released without this service.

import { COMPATIBILITY } from "./compat.js";
import { isKitRawCode } from "./codes.js";
import { releaseGate } from "./release-gate.js";
import { sha256Text } from "./sha256.js";
import { baseUrlProblem, createTranslatorClient, isServiceToken } from "./translator-client.js";

export const MODES = Object.freeze(["none", "http", "binding"]);
export const CACHE_MS = COMPATIBILITY.timing.handshake_cache_ms;

// ------------------------------------------------------------------------------------------------- the shape check

const SHA = /^[0-9a-f]{64}$/;
const ID = /^[A-Za-z0-9._:-]{1,128}$/;
const VERSION = /^[0-9A-Za-z.+-]{1,40}$/;
const SCHEMA = /^epinoic\.[a-z0-9.-]{1,120}$/;
const TS = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/;
const RT = /^KIT-RT-[0-9]{3}$/;
const isPlain = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const str = (re, min = 0, max = Infinity) => (v) => typeof v === "string" && (re === null || re.test(v)) && [...v].length >= min && [...v].length <= max;
const lit = (x) => (v) => v === x;
const oneOf = (...xs) => (v) => xs.includes(v);
const int = (min = -Infinity, max = Infinity) => (v) => Number.isSafeInteger(v) && v >= min && v <= max;
const bool = (v) => v === true || v === false;
const list = (f, min = 0, max = Infinity) => (v) => Array.isArray(v) && v.length >= min && v.length <= max && v.every(f);
const orNull = (f) => (v) => v === null || f(v);
const obj = (required, optional = {}) => (v) => {
  if (!isPlain(v)) return false;
  for (const k of Object.keys(v)) if (!Object.hasOwn(required, k) && !Object.hasOwn(optional, k)) return false;
  for (const [k, f] of Object.entries(required)) if (!Object.hasOwn(v, k) || !f(v[k])) return false;
  for (const [k, f] of Object.entries(optional)) if (Object.hasOwn(v, k) && !f(v[k])) return false;
  return true;
};
const routerIdentity = obj({ name: str(/^[a-z0-9][a-z0-9._-]{0,63}$/), version: str(/^[0-9]{1,4}(?:\.[0-9]{1,4}){0,3}$/), rules_sha256: str(SHA), cost_data_sha256: str(SHA) });
const CAPABILITIES = obj({
  schema: lit("epinoic.integration.capabilities.v1"),
  protocol: lit("epinoic.integration.v1"),
  service_env: oneOf("development", "staging", "production", "sim"),
  versions: obj({ ir: str(VERSION), engine: str(VERSION), policy: str(VERSION), translator: str(VERSION), z3: str(VERSION), contract: str(VERSION) }),
  build: obj({ build_id: str(SHA), schema_id: str(SHA), policy_id: str(SHA) }),
  selftest: obj({ passed: bool, digests: list(str(SHA), 3, 3) }),
  ports: obj({
    specialist: obj({ version: lit("1.0"), accepted: list(obj({ result: str(SCHEMA), runtime: str(SCHEMA), log: str(SCHEMA) }), 1, 8) }),
    checks: obj({ version: lit("1.0"), modes: list(oneOf("single", "duplicate", "combined"), 1, 3), named_policies: list(str(null, 1, 200), 1, 8),
      stem: obj({ branches: list(str(null, 1, 200), 1, 8), report_budget_max_s: int(1, 60) }) }),
    overseer: obj({ version: lit("1.0"), mode: oneOf("embedded", "sidecar"), auditor_version: str(VERSION), pack_digests: list(str(SHA), 1, 16),
      replay_mode: lit("process"), inline_final_release: lit(false), agents: oneOf("off", "async"), profiles: list(oneOf("standard", "fast"), 1, 2) }),
    translation: obj({ provider: oneOf("fixture", "anthropic", "openai_compatible"), tier: lit("cheapest"), live: bool, reviewer: lit("none") }),
    combinator: obj({ version: lit("1.0"), available: bool }, { instruction_pack: orNull(obj({ name: str(/^[a-z0-9][a-z0-9-]{0,63}$/), version: str(VERSION), sha256: str(SHA) })) }),
    router: obj({ version: lit("1.0"), required: lit(false), attached: bool, floor: obj({ name: lit("minimum-oversight-floor/1"), rules_sha256: str(SHA) }) },
      { identity: orNull(routerIdentity), refusal: orNull(str(RT)) }),
  }),
  subject_map: obj({ version: str(/^[0-9]{4}-[0-9]{2}-[0-9]{2}\.[0-9]{1,3}$/), sha256: str(SHA) }),
  policies: list(oneOf("verified-v1", "verified-v1-qualify"), 1, 2),
  limits: obj({ max_body_bytes: int(1024), max_answer_bytes: int(1), max_answers: int(1, 2), max_translated_claims: int(0, 64), checks_min_ms: int(1),
    checks_max_ms: int(1), turn_slots: int(1) }),
  signing: obj({ verdict_alg: lit("hmac-sha256"), verdict_key_id: str(ID), engine_key_id: str(ID) }),
  issued_at: str(TS),
});

const sameSet = (a, b) => JSON.stringify([...a].sort()) === JSON.stringify([...b].sort());

/** The refusals a router's attachment can give (protocol.ROUTER_ATTACH_REFUSALS). */
export const ROUTER_ATTACH_REFUSALS = Object.freeze(["KIT-RT-015", "KIT-RT-016"]);

/** The floor's reserved identity (protocol.FLOOR_IDENTITY_PREFIX): no attached router is named by it. */
export const FLOOR_IDENTITY_PREFIX = "minimum-oversight-floor";

/** A coherent router report: attached exactly with an identity, no refusal when attached, a refusal an attachment can give,
 * and no router named by the floor's reserved identity. */
function routerCoherent(r) {
  const identity = r.identity ?? null;
  const refusal = r.refusal ?? null;
  if (r.attached !== (identity !== null) || (r.attached && refusal !== null)) return false;
  if (identity !== null && identity.name.startsWith(FLOOR_IDENTITY_PREFIX)) return false;
  return refusal === null || ROUTER_ATTACH_REFUSALS.includes(refusal);
}

/** The Worker's handshake rules: { ok, code, rawCode, router }. The same order and codes as handshake.evaluate. */
export function evaluateCapabilities(raw, { workerEnv, base = "M" }) {
  const refuse = (code, router = null) => ({ ok: false, code, rawCode: "kit_hs_mismatch", router });
  if (!isPlain(raw) || raw.protocol !== "epinoic.integration.v1" || raw.schema !== "epinoic.integration.capabilities.v1") return refuse("KIT-HS-001");
  if (!CAPABILITIES(raw) || !routerCoherent(raw.ports.router)) return refuse("KIT-HS-001");
  const router = raw.ports.router;
  const accepted = COMPATIBILITY.components;
  for (const name of ["ir", "engine", "policy", "translator", "contract"]) if (!accepted[name].includes(raw.versions[name])) return refuse("KIT-HS-002", router);
  if (raw.selftest.passed !== true) return refuse("KIT-HS-004", router);
  if (!sameSet(raw.ports.checks.stem.branches, COMPATIBILITY.stem_branches)) return refuse("KIT-HS-005", router);
  if (!sameSet(raw.ports.checks.named_policies, COMPATIBILITY.named_policies)) return refuse("KIT-HS-006", router);
  const ov = raw.ports.overseer;
  if (!COMPATIBILITY.overseer.modes.includes(ov.mode) || ov.replay_mode !== "process" || ov.inline_final_release !== false) return refuse("KIT-HS-007", router);
  const liveRequired = workerEnv === "staging" || workerEnv === "production";
  if (liveRequired && raw.ports.translation.live !== true) return refuse("KIT-HS-009", router);
  if (!liveRequired && raw.ports.translation.live === true && workerEnv === "sim") return refuse("KIT-HS-009", router);
  if (raw.subject_map.sha256 !== COMPATIBILITY.subject_map.sha256) return refuse("KIT-HS-010", router);
  const pairs = raw.ports.specialist.accepted.map((p) => `${p.result}|${p.runtime}`);
  if (!sameSet(pairs, COMPATIBILITY.specialist_pairs.map((p) => `${p.result}|${p.runtime}`))) return refuse("KIT-HS-011", router);
  if (raw.service_env !== workerEnv) return refuse("KIT-HS-012", router);
  const lim = COMPATIBILITY.limits;
  if (raw.limits.max_body_bytes < lim.worker_max_request_bytes || raw.limits.max_answer_bytes < lim.max_answer_bytes || !raw.ports.checks.modes.includes("single")) {
    return refuse("KIT-HS-013", router);
  }
  const t = COMPATIBILITY.timing;
  const b = t.bases[base];
  if (!b || b.specialist_ceiling_ms + raw.limits.checks_min_ms + b.checks_tail_ms + t.completion_reserve_ms > b.deadline_ms) return refuse("KIT-HS-016", router);
  return { ok: true, code: null, rawCode: null, router };
}

// ------------------------------------------------------------------------------------------------- configuration and readiness

/** Local development: APP_ENV "development" (or unset, as in the kit's own tests). The verified backend runs there only on a
 * loopback host (handler.js chatBackendMode, isLocalDevelopment). */
const isDevelopmentEnv = (env) => env.APP_ENV === undefined || env.APP_ENV === "development";

/** True when the simulation switch KIT_SIMULATION is set at all (any non-empty value). */
const simulationSwitchSet = (env) => env.KIT_SIMULATION !== undefined && env.KIT_SIMULATION !== null && env.KIT_SIMULATION !== "";

/**
 * The Worker environment label the service must report (APP_ENV development | staging | production; sim in the
 * simulation). The simulation switch KIT_SIMULATION="1" is honoured only in local development: on staging, production
 * or any other APP_ENV it never turns the label into "sim" (so the handshake still requires a live provider and the
 * hosted environment's own label there), and configProblem() refuses the configuration (simulation_on_hosted).
 */
export function workerEnvOf(env) {
  if (env.KIT_SIMULATION === "1" && isDevelopmentEnv(env)) return "sim";
  return env.APP_ENV === "staging" ? "staging" : env.APP_ENV === "production" ? "production" : "development";
}

/**
 * createVerification({ env, binding, inner, fetchImpl, now, base }) -> { configProblem, ready, client, rawCode, workerEnv }.
 * `inner` is the inner orchestrator (base M: the simulation's specialist orchestrator; base P: the pilot).
 */
export function createVerification({ env, binding = null, inner = null, fetchImpl = fetch, now = Date.now, base = "M" } = {}) {
  const mode = env.TRANSLATOR_MODE ?? "none";
  const token = env.TRANSLATOR_SERVICE_TOKEN;
  const workerEnv = workerEnvOf(env);
  const client = mode === "http" || mode === "binding" ? createTranslatorClient({ mode, baseUrl: env.TRANSLATOR_BASE_URL, token, binding, fetchImpl, now }) : null;
  let cache = null; // { at, outcome } for this object's lifetime (one request in the handler)

  function configProblem() {
    if (simulationSwitchSet(env) && !isDevelopmentEnv(env)) return "simulation_on_hosted";
    if (!MODES.includes(mode) || mode === "none") return "translator_mode";
    if (mode === "http" && baseUrlProblem(env.TRANSLATOR_BASE_URL ?? "") !== null) return "translator_url";
    if (mode === "binding" && (binding === null || typeof binding.fetch !== "function")) return "translator_binding";
    if (!isServiceToken(token)) return "translator_token";
    if (inner === null || typeof inner.handle !== "function") return "inner_orchestrator";
    const t = COMPATIBILITY.timing;
    const b = t.bases[base];
    if (!b || b.specialist_ceiling_ms + COMPATIBILITY.limits.checks_min_ms + b.checks_tail_ms + t.completion_reserve_ms > b.deadline_ms) return "timing";
    return null;
  }

  async function ready({ signal } = {}) {
    if (cache !== null && now() - cache.at < CACHE_MS) return cache.outcome;
    if (client === null) return { ok: false, rawCode: "kit_hs_not_ready" };
    const r = await client.capabilities({ signal });
    let outcome;
    if (!r.ok) outcome = { ok: false, rawCode: r.code === "verifier_cancelled" ? "kit_hs_not_ready" : "kit_hs_unreachable" };
    else {
      const e = evaluateCapabilities(r.body, { workerEnv, base });
      outcome = e.ok ? { ok: true, capabilities: r.body, router: e.router } : { ok: false, rawCode: e.rawCode, code: e.code };
    }
    // Only a compatible answer is cached: a refresh failure leaves the backend not ready and is retried next turn.
    cache = outcome.ok ? { at: now(), outcome } : null;
    if (outcome.ok) api.lastCapabilities = outcome.capabilities;
    return outcome;
  }

  /** The raw code a verified-backend outcome is stored under: only codes of codes.js, never a free string. */
  function rawCode(outcome) {
    const raw = outcome?.kit?.rawCode;
    return isKitRawCode(raw) ? raw : undefined;
  }

  /**
   * turn.js's release gate after its own (async: the digest needs crypto.subtle): the verified backend releases only an
   * answer composed from its verdict, and only the exact text that verdict's deliverable names (delivery rule condition
   * 11, checked here again whatever produced the outcome, so a result passed through unchanged with a verdict of its own
   * cannot carry another text): kit_gate_binding otherwise.
   */
  async function releaseGateFor(outcome, result) {
    const verdict = outcome?.kit?.verdict;
    if (verdict === undefined || verdict === null) return { rawCode: "kit_gate_binding" };
    if (verdict?.delivery?.decision !== "deliver") return releaseGate(verdict, result); // kit_gate_decision
    const digest = verdict.delivery.deliverable?.answer_sha256;
    if (!isPlain(result) || typeof result.text !== "string" || typeof digest !== "string") return { rawCode: "kit_gate_binding" };
    let textDigest;
    try {
      textDigest = await sha256Text(result.text);
    } catch {
      return { rawCode: "kit_gate_binding" };
    }
    if (textDigest !== digest) return { rawCode: "kit_gate_binding" };
    return releaseGate(verdict, result);
  }

  const api = { configProblem, ready, client, rawCode, releaseGate: releaseGateFor, workerEnv, base, lastCapabilities: null };
  return api;
}
