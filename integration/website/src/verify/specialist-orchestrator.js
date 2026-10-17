// BASE M SIMULATION ONLY: an inner orchestrator over an injected specialist runtime (website/PATCH-PLAN.md, W3).
//
// Invariants:
// - it refuses to build unless the caller passes the runtime explicitly: a deployed Worker never constructs it (the
//   default export passes only { ctx }, so a Worker without an inner orchestrator answers chat_unavailable);
// - it returns the runtime's frozen result and its redactForLog projection unchanged, for the specialist port; it never
//   writes a ChatResult answer itself and never says review "passed": the decorator (with-verification.js) composes
//   the answer only from a verdict that says deliver;
// - every outcome other than "answer" is a closed error with the raw code specialist_<outcome> (codes.js);
// - `live` is false: the simulation's specialist is never a paid call.

import { publicCodeFor } from "./codes.js";

const OUTCOME = /^[a-z_]{1,40}$/;

/**
 * createSpecialistOrchestrator({ runtime, redactForLog, bundleFor, turnInputFor, failure, environment })
 * - runtime: an offline runtime (runSpecialistTurn, getCapabilities);
 * - redactForLog: the runtime package's own redactForLog;
 * - bundleFor(slug): the verified bundle for a slug;
 * - turnInputFor({ slug, bundle, request, context }): the runSpecialistTurn input (the simulation's authorizedGenerate
 *   returns the corpus item's recorded answer);
 * - failure(requestId, publicCode): the website's error ChatResult.
 */
export function createSpecialistOrchestrator({ runtime, redactForLog, bundleFor, turnInputFor, failure, environment = "offline-test" } = {}) {
  if (!runtime || typeof runtime.runSpecialistTurn !== "function") {
    throw new TypeError("the specialist orchestrator is for the simulation only: pass its runtime explicitly");
  }
  if (typeof redactForLog !== "function" || typeof bundleFor !== "function" || typeof turnInputFor !== "function" || typeof failure !== "function") {
    throw new TypeError("the specialist orchestrator needs redactForLog, bundleFor, turnInputFor and failure");
  }
  return Object.freeze({
    simulationOnly: true,
    async capabilities() {
      return runtime.getCapabilities({ environment });
    },
    async handle(request, context) {
      const bundle = await bundleFor(context.slug);
      const result = await runtime.runSpecialistTurn(turnInputFor({ slug: context.slug, bundle, request, context }));
      if (result?.outcome !== "answer") {
        const outcome = typeof result?.outcome === "string" && OUTCOME.test(result.outcome) ? result.outcome : "failed";
        if (outcome === "cancelled") return { ...failure(context.requestId, "turn_cancelled"), kit: { rawCode: null, simulated: true } };
        const raw = publicCodeFor(`specialist_${outcome}`) !== undefined ? `specialist_${outcome}` : "specialist_failed";
        return { ...failure(context.requestId, "review_unresolved"), kit: { rawCode: raw, simulated: true } };
      }
      return { specialist: { result, redacted: redactForLog(result), live: false } };
    },
  });
}
