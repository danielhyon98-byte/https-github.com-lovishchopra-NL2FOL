// The reply the simulation's drivers give a runtime copy through its authorizedGenerate callback, in the shape that
// copy's own runtime contract takes (integration/sim/README.md, "The two copies"):
//
// - epinoic.specialist-runtime.v0.1.0 (the harness): the objects the drivers have always returned, unchanged:
//   {status: "completed", output: {text, finishReason: "stop"}, usage: null, providerEvidence: null}, and for a turn
//   without a recorded answer {status: "failed", error: {code}, usage: null, providerEvidence: null};
// - epinoic.specialist-runtime.v0.2.0 (the retrained repository): the website's generation result, built by the copy's
//   own synthetic callbacks module (specialist-runtime/fixtures/synthetic/callbacks.js): generationResult({text}) and,
//   without a recorded answer, failureResult({code: "provider_error"}) (v0.2.0 takes only its closed failure codes).
//
// Nothing of the agents repositories is copied into the kit: the v0.2.0 builders are the copy's own module, passed in.
// Any other contract throws "unsupported runtime contract": a driver reports it and does not run (exit 3), never guesses.
//
//   import { replyFor } from "./runtime-reply.mjs";
//   const reply = replyFor(RUNTIME_CONTRACT_VERSION, callbacksModuleOfTheCopy);
//   reply.generated(text); reply.notGenerated("sim_no_answer");

export const SUPPORTED_CONTRACTS = Object.freeze(["epinoic.specialist-runtime.v0.1.0", "epinoic.specialist-runtime.v0.2.0"]);

export function replyFor(contract, callbacks) {
  if (contract === "epinoic.specialist-runtime.v0.1.0") {
    return Object.freeze({
      generated: (text) => ({ status: "completed", output: { text, finishReason: "stop" }, usage: null, providerEvidence: null }),
      notGenerated: (code) => ({ status: "failed", error: { code }, usage: null, providerEvidence: null }),
    });
  }
  if (contract === "epinoic.specialist-runtime.v0.2.0") {
    if (typeof callbacks?.generationResult !== "function" || typeof callbacks?.failureResult !== "function") {
      throw new Error("unsupported runtime contract epinoic.specialist-runtime.v0.2.0 without the copy's generationResult and failureResult");
    }
    return Object.freeze({
      generated: (text) => callbacks.generationResult({ text }),
      notGenerated: () => callbacks.failureResult({ code: "provider_error" }),
    });
  }
  throw new Error(`unsupported runtime contract ${contract}: the simulation replies to ${SUPPORTED_CONTRACTS.join(" and ")} only`);
}
