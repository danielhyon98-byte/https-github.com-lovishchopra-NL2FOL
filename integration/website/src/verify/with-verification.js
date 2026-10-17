// The verified backend's orchestrator decorator (protocol epinoic.integration.v1; PROTOCOL.md section 9, the delivery rule).
//
// Order (each step names its refusal; the first that fails decides):
//   subject check (check 5) -> stillPending -> inner.handle (the specialist) -> stillPending -> the checks call ->
//   binding and re-derivation (release-gate.js, row 1) -> the decision -> compose the ChatResult with its checks.
//
// Invariants:
// - Z3 and STEM checks are required: no answer is ever returned without a verdict that says deliver, bound to this
//   turn, this attempt, this student text and this exact answer; a non-success is never shown as success;
// - the decorator never produces review "passed" or "not_required": a delivered answer says "checks:integration.v1";
// - every refusal after the specialist call is final and carries one raw code of codes.js in `kit.rawCode`
//   (turn.js stores it; history shows the same public code POST answered);
// - `kit` (rawCode, simulated, verdict) is for turn.js only: it is removed before the result is validated, stored or
//   returned; `simulated` is true unless both the specialist and the checks were live;
// - the subject routing is one slug or nothing (router-port.js): never a fan-out, never another specialist.

import { COMPATIBILITY } from "./compat.js";
import { publicCodeFor, rawCodeForReason } from "./codes.js";
import { bindingProblem, checksFromVerdict, VERIFIED_REVIEW } from "./release-gate.js";
import { decideSpecialist } from "./router-port.js";
import { sha256Text } from "./sha256.js";
import { envelopeFor, PortRefusal } from "./specialist-port.js";

const LIMITS = COMPATIBILITY.limits;

/** The checks budget for a turn whose deadline is `deadlineAt`: what is left after the checks tail and the completion
 * reserve, at most checks_max_ms; null when less than checks_min_ms is left (the checks cannot run: incomplete). */
export function checksBudgetMs(deadlineAt, now, base = "M") {
  const t = COMPATIBILITY.timing;
  const b = t.bases[base];
  const left = deadlineAt - now - b.checks_tail_ms - t.completion_reserve_ms;
  if (!Number.isFinite(left) || left < LIMITS.checks_min_ms) return null;
  return Math.min(LIMITS.checks_max_ms, Math.floor(left));
}

/**
 * withVerification(inner, deps) -> { handle(request, context) } in the website's orchestrator contract: each call
 * resolves { status, result, kit } (the result a ChatResult; `kit` for turn.js only).
 * deps: { verification, failure(requestId, publicCode) -> { status, result }, environment, policy, now, base }.
 * context (from turn.js): { requestId, signal, route: { routeId }, turn: { turnId, attemptId }, deadlineAt, stillPending }.
 */
export function withVerification(inner, deps) {
  if (inner === null || inner === undefined || typeof inner.handle !== "function") throw new TypeError("withVerification needs an inner orchestrator");
  const { verification, failure, environment, policy = "verified-v1", now = Date.now, base = "M" } = deps;

  return {
    async handle(request, context) {
      const refuse = (rawCode) => ({ ...failure(context.requestId, publicCodeFor(rawCode) ?? "upstream_invalid"), kit: { rawCode, simulated: true } });
      const cancelled = () => ({ ...failure(context.requestId, "turn_cancelled"), kit: { rawCode: null, simulated: true } });

      // Check 5: the routed subject is mapped and its specialist is available.
      const capabilities = typeof inner.capabilities === "function" ? await inner.capabilities() : null;
      const decision = decideSpecialist({ routeId: context.route?.routeId }, { environment, capabilities });
      if (decision.kind !== "slug") return refuse(decision.rawCode ?? "specialist_unmapped");
      if (!(await context.stillPending())) return cancelled();

      // The specialist (the inner orchestrator); every outcome other than an answer is the base's own closed error.
      const produced = await inner.handle(request, { ...context, slug: decision.slug });
      if (produced?.specialist === undefined) return produced;
      if (!(await context.stillPending())) return cancelled();

      let envelope;
      try {
        envelope = await envelopeFor(produced.specialist.result, produced.specialist.redacted, { agentId: decision.slug });
      } catch (err) {
        if (err instanceof PortRefusal) return refuse(err.code === "KIT-REQ-012" ? `specialist_${produced.specialist.result?.outcome ?? "failed"}` : "specialist_failed");
        throw err;
      }

      const budget = checksBudgetMs(context.deadlineAt, now(), base);
      if (budget === null) return refuse("verifier_timeout");
      const userText = request.message;
      const turnRequest = {
        schema: "epinoic.integration.turn-check.v1",
        protocol: "epinoic.integration.v1",
        mode: "single",
        ids: { task_id: context.turn.turnId, request_id: context.turn.attemptId },
        task: { route: context.route.routeId, slug: decision.slug, subject: decision.subject, course_level: "unknown", task_type: "short_answer",
          user_text: userText, user_text_sha256: await sha256Text(userText), supplied_texts: [] },
        answers: [envelope],
        policy,
        budget_ms: budget,
        revision_of: null,
      };
      const timeoutMs = budget + COMPATIBILITY.timing.bases[base].checks_tail_ms;
      const call = await verification.client.checkTurn(turnRequest, { signal: context.signal, timeoutMs });
      if (!call.ok) return refuse(call.code);

      // Row 1: the verdict is well formed, bound to this attempt and consistent with itself.
      const verdict = call.body;
      const problem = await bindingProblem(verdict, {
        taskId: context.turn.turnId, requestId: context.turn.attemptId, userText, policy, mode: "single",
        answers: [[decision.slug, envelope.answer, envelope.result_sha256]],
        releaseText: verdict?.delivery?.decision === "deliver" ? envelope.answer : null, revisionOf: null,
      });
      if (problem !== null) return refuse(problem[0]);
      if (verdict.delivery.decision !== "deliver") return refuse(rawCodeForReason(verdict.delivery.reasons?.[0]) ?? "kit_dl_006");
      if (!(await context.stillPending())) return cancelled();

      const { checks, checksSummary } = checksFromVerdict(verdict);
      const live = produced.specialist.live === true && verification.lastCapabilities?.ports?.translation?.live === true;
      const result = {
        kind: "answer",
        requestId: context.requestId,
        conversationId: request.conversationId,
        turnVersion: request.expectedTurnVersion + 1,
        specialist: context.route.routeId,
        text: envelope.answer,
        references: [],
        review: VERIFIED_REVIEW,
        checks,
        checksSummary,
      };
      return { status: 200, result, kit: { rawCode: null, simulated: !live, verdict } };
    },
  };
}
