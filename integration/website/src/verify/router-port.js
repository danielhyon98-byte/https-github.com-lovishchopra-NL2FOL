// From a routing decision to one specialist slug (integration/README.md, "router-port.js"; subject map of PROTOCOL.md
// section 2). This is the website's subject routing, not the flash router of the overseer (that one is a separate
// sub-agent behind the translator's router port and never runs in the Worker).
//
// Invariants:
// - a website route decision (routeId "history" | "english") or an agents RoutingResult (route | clarify | unavailable)
//   becomes exactly one slug of the subject map for this environment, or a clarification, or "unavailable": never a
//   fan-out to several specialists;
// - a route the subject map does not hold for this environment is specialist_unmapped; a mapped slug the runtime does
//   not report available is specialist_unavailable (PROTOCOL.md section 3, check 5); neither falls back to another specialist;
// - combined mode starts only from clarify/mixed_request plus the student's explicit choice (decision D19), which v1
//   does not offer on the website.

import { SUBJECT_MAP } from "./subject-map.js";

/** The subject-map row for a website route in an environment, or null. */
export function entryForRoute(routeId, environment) {
  return SUBJECT_MAP.entries.find((e) => e.route === routeId && e.environments.includes(environment)) ?? null;
}

/** The subject-map row for an agents slug in an environment ("service" rows are usable by the service-side driver). */
export function entryForSlug(slug, environment) {
  return SUBJECT_MAP.entries.find((e) => e.slug === slug && (e.environments.includes(environment) || e.environments.includes("service"))) ?? null;
}

/**
 * One decision: { kind: "slug", slug, subject, route } | { kind: "clarify", reason } | { kind: "unavailable", rawCode }.
 * `capabilities` is the runtime's getCapabilities({environment}) answer: { specialists: [{ slug, available }] }.
 */
export function decideSpecialist(decision, { environment, capabilities }) {
  let entry = null;
  if (decision?.outcome === "clarify") return { kind: "clarify", reason: typeof decision.reason === "string" ? decision.reason : "clarify" };
  if (decision?.outcome === "unavailable") return { kind: "unavailable", rawCode: "specialist_unavailable" };
  if (decision?.outcome === "route" && typeof decision.slug === "string") entry = entryForSlug(decision.slug, environment);
  else if (typeof decision?.routeId === "string") entry = entryForRoute(decision.routeId, environment);
  if (entry === null) return { kind: "unavailable", rawCode: "specialist_unmapped" };
  const listed = (capabilities?.specialists ?? []).find((s) => s.slug === entry.slug);
  if (!listed || listed.available !== true) return { kind: "unavailable", rawCode: "specialist_unavailable" };
  return { kind: "slug", slug: entry.slug, subject: entry.subject, route: entry.route };
}
