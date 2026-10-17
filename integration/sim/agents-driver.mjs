// The simulation's agents driver (PROTOCOL.md section 14.5): without the website, the agents repository's router
// (specialist-routing's selectSpecialist over its synthetic catalogue and fixtures) -> the kit's router-port.js (one
// slug, a clarification, or unavailable: never a fan-out) -> the agents repository's offline runtime
// (createOfflineTestRuntime over its synthetic bundle; authorizedGenerate returns each corpus item's recorded answer) ->
// the specialist port (the kit's A2 envelope builder, integration/agents/checks-port/src/envelope.js) -> the checks
// service on loopback, for the STEM, duplicate, combined and clarify turns of users.json (path "agents"), and for the STEM
// fault cases.
//
// Invariants: it runs on a COPY of the agents repository (git archive), never a checkout, and never writes into it;
// fetch is limited to loopback; the runtime and the router are the copy's own code, unchanged; a mixed request is a
// clarification and makes no specialist or checks call; every verdict it records is the service's own answer. Without
// the service (--service) or the copy it exits 3 and names what is missing.
//
// Usage: node agents-driver.mjs --agents <copy> --service <http://127.0.0.1:port> --token-file <file> --users <users.json>
//        --corpus <service corpus copy> --round <round> --out <dir> [--faults <faults.json>]
//
// Writes <out>/agents-driver.json (schema epinoic.integration.sim-agents-records.v1).
import { createHash, randomUUID } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const args = {};
for (let i = 0; i < argv.length; i += 1) if (argv[i].startsWith("--")) args[argv[i].slice(2)] = argv[i + 1];

const AGENTS_FILES = ["specialist-runtime/src/index.js", "specialist-runtime/fixtures/synthetic/harness.js", "specialist-runtime/fixtures/synthetic/gate-config.js",
  "specialist-runtime/fixtures/synthetic/manifest.js", "specialist-runtime/fixtures/synthetic/synthetic-bundle.txt", "specialist-routing/package.json",
  "specialist-routing/src/index.js", "specialist-routing/fixtures/catalogue.synthetic.json", "specialist-routing/fixtures/policy.synthetic.json",
  "specialist-routing/fixtures/harness.synthetic.json"];
const missing = [];
for (const f of AGENTS_FILES) if (!args.agents || !existsSync(join(args.agents, f))) missing.push(f);
if (!args.service) missing.push("a running checks service (--service)");
for (const k of ["token-file", "users", "corpus", "round", "out"]) if (!args[k]) missing.push(`--${k}`);
if (missing.length > 0) {
  console.error(`not runnable: missing ${missing.join(", ")}`);
  process.exit(3);
}

const LOOPBACK = new Set(["127.0.0.1", "localhost", "[::1]"]);
const urlOf = (input) => (input instanceof URL ? input : new URL(typeof input === "string" ? input : input.url));
const fetchLog = { loopback: 0, refused: [] };
const realFetch = globalThis.fetch;
globalThis.fetch = async (input, init) => {
  const url = urlOf(input);
  if (!LOOPBACK.has(url.hostname)) {
    fetchLog.refused.push(url.hostname);
    throw new Error(`the simulation refuses non-loopback host ${url.hostname}`);
  }
  fetchLog.loopback += 1;
  return realFetch(input, init);
};

const AGENTS = resolve(args.agents);
const fromAgents = (p) => import(pathToFileURL(join(AGENTS, p)).href);
const runtimePackage = await fromAgents("specialist-runtime/src/index.js");
const harness = await fromAgents("specialist-runtime/fixtures/synthetic/harness.js");
const gates = await fromAgents("specialist-runtime/fixtures/synthetic/gate-config.js");
const manifests = await fromAgents("specialist-runtime/fixtures/synthetic/manifest.js");
const routing = await fromAgents("specialist-routing/src/index.js");
const { buildEnvelope } = await import(pathToFileURL(join(HERE, "..", "agents", "checks-port", "src", "envelope.js")).href);
const { decideSpecialist } = await import(pathToFileURL(join(HERE, "..", "website", "src", "verify", "router-port.js")).href);

const SERVICE = new URL(args.service);
if (!LOOPBACK.has(SERVICE.hostname)) {
  console.error("not runnable: the checks service must be on a loopback host");
  process.exit(3);
}
const TOKEN = readFileSync(args["token-file"], "utf8").trim();
const USERS = JSON.parse(readFileSync(args.users, "utf8"));
const ROUND_DIR = join(args.corpus, args.round);
const FAULTS = args.faults ? JSON.parse(readFileSync(args.faults, "utf8")) : [];
const sha256 = (text) => createHash("sha256").update(text, "utf8").digest("hex");
const corpusItem = (name) => {
  const p = join(ROUND_DIR, "specialists", `${name}.json`);
  return existsSync(p) ? JSON.parse(readFileSync(p, "utf8")) : null;
};

// The router: the copy's selectSpecialist over its synthetic fixtures (as its own test helpers set it up), with the
// classifier's evidence written by the simulation for each turn (no inference).
const readRouting = (rel) => JSON.parse(readFileSync(join(AGENTS, "specialist-routing", rel), "utf8"));
const catalogue = readRouting("fixtures/catalogue.synthetic.json");
const policy = readRouting("fixtures/policy.synthetic.json");
const routerHarness = readRouting("fixtures/harness.synthetic.json");
const labelSet = routing.buildLabelSet(catalogue);
const routerIds = { catalogueSha256: await routing.catalogueDigest(catalogue), labelSetSha256: await routing.labelSetDigest(labelSet) };
const routerOptions = { offlineFixtureHarness: true, limits: structuredClone(routerHarness.limits), calibrationContext: structuredClone(routerHarness.calibrationContext) };
function evidence(subjects, flags = {}) {
  return {
    schema: "epinoic.routing-evidence.v1", labelSetVersion: labelSet.labelSetVersion, labelSetSha256: routerIds.labelSetSha256, catalogueSha256: routerIds.catalogueSha256,
    adapter: { ...routerHarness.adapter }, excerpt: { version: routerHarness.excerpt.version, utf8Bytes: 64, codePoints: 64, truncated: false },
    subjects: Object.entries(subjects).map(([label, score]) => ({ label, score })), families: [],
    flags: { out_of_scope: 0, mixed_request: 0, non_english_input: 0, needs_task_context: 0, ...flags },
  };
}
// The router reads the availability of the runtime it routes to (the runtime's own getCapabilities answer, limited to
// the catalogue's subjects), not the router fixture's: the simulation's runtime holds the synthetic History, English
// and Physics specialists.
const catalogueSlugs = new Set(catalogue.subjects.map((x) => x.slug));
function runtimeCapabilitiesForRouter() {
  const caps = runtime.getCapabilities({ environment: "offline-test" });
  return { ...caps, entries: caps.entries.filter((e) => catalogueSlugs.has(e.slug)) };
}
const route = (subjects, flags) => routing.selectSpecialist({ evidence: evidence(subjects, flags), catalogue, labelSet, policy,
  capabilities: runtimeCapabilitiesForRouter(), options: routerOptions });

// The runtime: the copy's synthetic manifest and gate configuration (History unchanged; the simulation's synthetic
// English and Physics specialists are the same entry under their slugs, with the sources line optional).
const SLUGS = ["history", "english-a-literature", "physics"];
const BUNDLE_BYTES = readFileSync(join(AGENTS, "specialist-runtime/fixtures/synthetic/synthetic-bundle.txt"));
const manifest = JSON.parse(JSON.stringify(manifests.SYNTHETIC_MANIFEST));
const historyEntry = manifest.entries.find((e) => e.slug === "history");
for (const slug of SLUGS.slice(1)) manifest.entries.push({ ...historyEntry, slug, displayName: `${slug} (SYNTHETIC simulation fixture)` });
const gateFor = (slug) => {
  const g = JSON.parse(JSON.stringify(gates.SYNTHETIC_GATE_CONFIG));
  return slug === "history" ? g : { ...g, slug, checks: { ...g.checks, "sources-line": { ...g.checks["sources-line"], required: false } } };
};
const runtime = runtimePackage.createOfflineTestRuntime({ manifest, gateConfigs: Object.fromEntries(SLUGS.map((s) => [s, gateFor(s)])) });
const bundles = new Map();
for (const slug of SLUGS) bundles.set(slug, await runtime.loadPinnedBundle({ slug, bundleModule: harness.moduleForBytes(BUNDLE_BYTES, { slug }), environment: "offline-test" }));
const SUBJECTS = { history: "History", "english-a-literature": "English A: Literature", physics: "Physics" };
const ROUTES = { history: "history", "english-a-literature": "english", physics: null };

const counts = { specialist: 0, check: 0 };
let seq = 0;
const newId = (prefix) => `${prefix}_${String((seq += 1)).padStart(6, "0")}_${randomUUID().replaceAll("-", "").slice(0, 16)}`;

async function specialistAnswer(slug, text, ids) {
  counts.specialist += 1;
  const result = await runtime.runSpecialistTurn({
    slug, mode: "pilot-single-turn-no-tools", environment: "offline-test", bundle: bundles.get(slug), message: ids.message, priorTurns: [],
    limits: harness.SYNTHETIC_LIMITS, turn: { conversationId: ids.conversationId, turnId: ids.taskId, turnVersion: 1, attemptId: ids.requestId },
    authorizedGenerate: async () => ({ status: "completed", output: { text, finishReason: "stop" }, usage: null, providerEvidence: null }),
  });
  return { result, redacted: runtimePackage.redactForLog(result) };
}

async function check(request) {
  counts.check += 1;
  const r = await globalThis.fetch(new URL("/v1/turns/check", SERVICE.origin), {
    method: "POST", body: JSON.stringify(request),
    headers: { Authorization: `Bearer ${TOKEN}`, "Epinoic-Protocol": "integration.v1", Accept: "application/json", "Content-Type": "application/json" },
  });
  const text = await r.text();
  let body = null;
  try {
    body = JSON.parse(text);
  } catch {
    body = null;
  }
  return { status: r.status, body };
}

const records = { schema: "epinoic.integration.sim-agents-records.v1", status: "ran", round: args.round,
  agents_commit: existsSync(join(AGENTS, ".kit-archive-commit")) ? readFileSync(join(AGENTS, ".kit-archive-commit"), "utf8").trim() : null,
  turns: [], faults: [], verdicts: [], fetch: fetchLog, not_run: [] };

/** One checks call for `items` (one answer each) in `mode`, after routing `subjects`. */
async function turn(user, action, items, { mode = "single", subjects, flags = {}, texts = null, faultCase = null } = {}) {
  const corpus = items.map(corpusItem);
  if (corpus.some((c) => c === null)) {
    records.not_run.push({ user, action, reason: `no corpus item among ${items.join(", ")}` });
    return null;
  }
  const before = { ...counts };
  const decision = await route(subjects, flags);
  // The subject map's rows for the simulation environment (sim) and the service-side rows (service).
  const routed = decideSpecialist(decision, { environment: "sim", capabilities: runtime.getCapabilities({ environment: "offline-test" }) });
  const rec = { user, action, items, mode, routing: { outcome: decision.outcome, reason: decision.reason, slug: decision.slug ?? null, candidates: decision.candidates.map((c) => c.slug) },
    port: routed.kind, fault_case: faultCase };
  if (routed.kind !== "slug") {
    rec.calls = { specialist: counts.specialist - before.specialist, check: counts.check - before.check };
    records.turns.push(rec);
    return rec;
  }
  // Duplicate: the routed specialist twice; combined: the routed specialist and the second item's specialist (only after
  // a clarification and the student's explicit choice, decision D19: here the simulation states that choice).
  const slugs = mode === "combined" ? [routed.slug, corpus[1].agent_id.replace(/-specialist$/, "")] : items.map(() => routed.slug);
  const agentIds = mode === "duplicate" ? slugs.map((s, i) => `${s}@${"ab"[i]}`) : slugs;
  const taskId = newId("t");
  const requestId = newId("a");
  const message = corpus[0].question;
  const envelopes = [];
  for (let i = 0; i < items.length; i += 1) {
    const text = texts?.[i] ?? corpus[i].response_text;
    const { result, redacted } = await specialistAnswer(slugs[i], text, { message, conversationId: `c_${taskId}`, taskId, requestId });
    if (result.outcome !== "answer") {
      rec.specialist_outcome = result.outcome;
      rec.calls = { specialist: counts.specialist - before.specialist, check: counts.check - before.check };
      records.turns.push(rec);
      return rec;
    }
    envelopes.push(await buildEnvelope(result, redacted, { agentId: agentIds[i] }));
  }
  const request = {
    schema: "epinoic.integration.turn-check.v1", protocol: "epinoic.integration.v1", mode, ids: { task_id: taskId, request_id: requestId },
    task: { route: ROUTES[routed.slug] ?? null, slug: routed.slug, subject: SUBJECTS[routed.slug], course_level: "unknown", task_type: corpus[0].task_type,
      user_text: message, user_text_sha256: sha256(message), supplied_texts: [] },
    answers: envelopes, policy: "verified-v1", budget_ms: 60000, revision_of: null,
  };
  const r = await check(request);
  rec.request_id = requestId;
  rec.status = r.status;
  rec.decision = r.body?.delivery?.decision ?? null;
  rec.reasons = r.body?.delivery?.reasons ?? null;
  rec.code = r.status === 200 ? null : (r.body?.code ?? r.body?.error?.code ?? null);
  rec.receipt = r.body?.receipt ?? null;
  rec.answer_sha256 = envelopes.map((e) => e.answer_sha256);
  rec.calls = { specialist: counts.specialist - before.specialist, check: counts.check - before.check };
  if (r.status === 200 && r.body) records.verdicts.push(r.body);
  records.turns.push(rec);
  return rec;
}

const SUBJECT_SCORES = { History: { history: 0.9 }, "English A: Literature": { "english-a-literature": 0.9 }, Physics: { physics: 0.9 } };
for (const u of USERS.users.filter((x) => x.path === "agents")) {
  for (const t of u.turns) {
    const item = corpusItem(t.item);
    const scores = item ? SUBJECT_SCORES[item.subject] ?? {} : {};
    if (t.action === "stem") await turn(u.user, t.action, [t.item], { subjects: scores });
    else if (t.action === "duplicate_clean" || t.action === "duplicate_conflicting") await turn(u.user, t.action, [t.item, t.second], { mode: "duplicate", subjects: scores });
    else if (t.action === "combined") await turn(u.user, t.action, [t.item, t.second], { mode: "combined", subjects: scores });
    else if (t.action === "clarify") await turn(u.user, t.action, [t.item], { subjects: { history: 0.8, physics: 0.8 } });
    else records.not_run.push({ user: u.user, action: t.action, reason: `action ${t.action} is not an agents-path action` });
  }
}
// The STEM fault cases (the arena's STEM mutations go through the specialist port; the website maps no STEM subject).
for (const f of FAULTS) {
  const item = corpusItem(f.item);
  if (item === null || item.subject !== "Physics") continue;
  const rec = await turn("sim-faults", `fault:${f.kind}`, [f.item], { subjects: SUBJECT_SCORES.Physics, texts: [f.text], faultCase: f.case });
  if (rec && rec.status !== undefined) {
    records.faults.push({ case: f.case, item: f.item, kind: f.kind, status: rec.status, decision: rec.decision, reasons: rec.reasons,
      website_refused: rec.status === 200 && rec.decision !== "deliver", website_codes: rec.receipt?.error_codes ?? [], receipt_status: rec.receipt?.status ?? null,
      website_labelled_checked: false, answer_sha256: sha256(f.text), path: "agents" });
  }
}

mkdirSync(args.out, { recursive: true });
writeFileSync(join(args.out, "agents-driver.json"), JSON.stringify(records, null, 1));
console.log(`agents driver: ${records.turns.length} turn(s), ${records.faults.length} fault case(s), ${records.not_run.length} not run; refused hosts: ${fetchLog.refused.length}`);
process.exit(0);
