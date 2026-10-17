// Outbound client of the translator's checks service (protocol epinoic.integration.v1; PROTOCOL.md sections 3 and 5).
//
// Invariants (the conventions of src/router/fastino.js):
// - one bounded request per call, never retried here; the caller decides what an unavailable service means, and it is
//   never a hidden substitute: no answer is released without a verdict;
// - transports: "http" (fetchImpl to an https base URL, http only on loopback) or "binding" (a Cloudflare service
//   binding's fetch); the bearer token and the service's bodies never leave this module; failures are closed codes;
// - a response is read only when it is 200 application/json and at most COMPATIBILITY.limits.worker_max_response_bytes,
//   and it must be strict protocol JSON (canonical-json.js parseStrict); anything else is verifier_malformed;
// - injectable fetchImpl and now(); an AbortSignal cancels; a timeout aborts the request.

import { COMPATIBILITY } from "./compat.js";
import { parseStrict } from "./canonical-json.js";

// Closed failure codes. `retryable` says whether the same request may succeed later unchanged.
export const VERIFIER_FAILURES = Object.freeze({
  verifier_busy: true, // this isolate already has its maximum of checks calls in flight
  verifier_cancelled: true, // the caller aborted (the turn's deadline or the person stopped waiting)
  verifier_timeout: true,
  verifier_network: true,
  verifier_redirect: false,
  verifier_auth: false, // 401 / 403: the token is missing, wrong or revoked
  verifier_rate_limited: true, // 429 E503: Retry-After
  verifier_capacity: true, // 503 E504: the service's solver slots are all busy
  verifier_rejected: false, // 400 with a KIT-REQ code, 413, or another 4xx: the request is out of contract
  verifier_error: true, // 5xx
  verifier_malformed: false, // anything but a 200 application/json strict protocol body of bounded size
});

export const PROTOCOL_HEADER = "integration.v1";
export const HANDSHAKE_TIMEOUT_MS = COMPATIBILITY.timing.handshake_timeout_ms;
const MAX_RESPONSE_BYTES = COMPATIBILITY.limits.worker_max_response_bytes;
const TOKEN = /^[\x21-\x7e]{16,512}$/;
const LOOPBACK = new Set(["127.0.0.1", "localhost", "[::1]"]);

export const isServiceToken = (value) => typeof value === "string" && TOKEN.test(value);

/** null when `url` is an acceptable base URL (https, or http on loopback only), else a closed problem label. */
export function baseUrlProblem(url) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return "translator_url";
  }
  if (parsed.username || parsed.password || parsed.search || parsed.hash) return "translator_url";
  if (parsed.protocol === "https:") return null;
  if (parsed.protocol === "http:" && LOOPBACK.has(parsed.hostname)) return null;
  return "translator_url";
}

const failure = (code, extra = {}) => ({ ok: false, code, retryable: VERIFIER_FAILURES[code], retryAfterSeconds: null, ...extra });

function retryAfter(headers) {
  const value = headers.get("Retry-After");
  return value !== null && /^\d{1,9}$/.test(value.trim()) ? Math.min(Number(value), 3600) : null; // capped at one hour
}

async function readLimitedText(response, limit) {
  if (!response.body) throw new Error("missing_body");
  const reader = response.body.getReader();
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit) {
        await reader.cancel();
        throw new Error("body_too_large");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
}

async function failureForStatus(response) {
  const status = response.status;
  if (status >= 300 && status < 400) return failure("verifier_redirect", { httpStatus: status });
  if (status === 401 || status === 403) return failure("verifier_auth", { httpStatus: status });
  if (status === 429) return failure("verifier_rate_limited", { httpStatus: status, retryAfterSeconds: retryAfter(response.headers) });
  if (status === 503) return failure("verifier_capacity", { httpStatus: status, retryAfterSeconds: retryAfter(response.headers) });
  if (status === 400 || status === 413 || (status >= 400 && status < 500)) {
    // A 400 names its closed KIT-REQ code; nothing else of the body is kept.
    let kitCode = null;
    try {
      const text = await readLimitedText(response, 4096);
      const m = /"code"\s*:\s*"(KIT-REQ-[0-9]{3}|E[0-9]{3})"/.exec(text);
      kitCode = m ? m[1] : null;
    } catch {
      kitCode = null;
    }
    return failure("verifier_rejected", { httpStatus: status, kitCode });
  }
  return failure("verifier_error", { httpStatus: status });
}

export function createConcurrencyLimit(max) {
  let active = 0;
  return {
    tryAcquire() {
      if (active >= max) return false;
      active += 1;
      return true;
    },
    release() {
      active = Math.max(0, active - 1);
    },
    get active() {
      return active;
    },
  };
}

const sharedLimit = createConcurrencyLimit(COMPATIBILITY.limits.turn_slots);

/**
 * createTranslatorClient({ mode, baseUrl, token, binding, fetchImpl, now, limit }) ->
 *   { capabilities({ signal }), checkTurn(request, { signal, timeoutMs }) }
 * Each resolves { ok: true, body, ms } or a closed failure { ok: false, code, retryable, ... , ms }.
 */
export function createTranslatorClient({ mode, baseUrl = "", token, binding = null, fetchImpl = fetch, now = Date.now, limit = sharedLimit } = {}) {
  const origin = mode === "binding" ? "https://translator.internal" : String(baseUrl).replace(/\/+$/, "");

  async function call(method, path, body, { signal, timeoutMs }) {
    const startedAt = now();
    const done = (outcome) => ({ ...outcome, ms: now() - startedAt });
    if (signal !== undefined && signal !== null && !(signal instanceof AbortSignal)) throw new TypeError("signal must be an AbortSignal");
    if (signal?.aborted) return done(failure("verifier_cancelled"));
    if (!limit.tryAcquire()) return done(failure("verifier_busy"));
    const controller = new AbortController();
    const forwardAbort = () => controller.abort();
    let timedOut = false;
    let timer;
    try {
      timer = setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, timeoutMs);
      signal?.addEventListener("abort", forwardAbort, { once: true });
      const init = {
        method,
        headers: { Authorization: `Bearer ${token}`, "Epinoic-Protocol": PROTOCOL_HEADER, Accept: "application/json",
          ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
        body: body !== undefined ? JSON.stringify(body) : undefined,
        redirect: "manual",
        signal: controller.signal,
      };
      let response;
      try {
        response = mode === "binding" ? await binding.fetch(`${origin}${path}`, init) : await fetchImpl(`${origin}${path}`, init);
      } catch {
        return done(failure(timedOut ? "verifier_timeout" : signal?.aborted ? "verifier_cancelled" : "verifier_network"));
      }
      if (response.status !== 200) {
        const out = await failureForStatus(response);
        await response.body?.cancel().catch(() => {});
        return done(out);
      }
      const type = response.headers.get("Content-Type")?.split(";")[0].trim().toLowerCase();
      if (type !== "application/json") {
        await response.body?.cancel().catch(() => {});
        return done(failure("verifier_malformed", { detail: "content_type" }));
      }
      let parsed;
      try {
        const text = await readLimitedText(response, MAX_RESPONSE_BYTES);
        parsed = parseStrict(text);
      } catch (cause) {
        if (timedOut) return done(failure("verifier_timeout"));
        if (signal?.aborted) return done(failure("verifier_cancelled"));
        return done(failure("verifier_malformed", { detail: cause?.message === "body_too_large" ? "too_large" : "json" }));
      }
      return done({ ok: true, body: parsed });
    } finally {
      limit.release();
      clearTimeout(timer);
      signal?.removeEventListener("abort", forwardAbort);
    }
  }

  return {
    capabilities({ signal } = {}) {
      return call("GET", "/v1/capabilities", undefined, { signal, timeoutMs: HANDSHAKE_TIMEOUT_MS });
    },
    checkTurn(request, { signal, timeoutMs }) {
      return call("POST", "/v1/turns/check", request, { signal, timeoutMs });
    },
  };
}
