// The simulation's website driver (PROTOCOL.md section 14.5, step 2): replays every simulated user of users.json whose path
// is "website" through the website path of a DISPOSABLE export of the website: POST /api/chat through the export's own
// handleRequest with the verified backend (patch set M), the export's tests/helpers/d1.js on node:sqlite, the mock
// subject router, synthetic loopback principals, and the checks service on loopback. The specialist is the agents
// repository's own offline runtime (createOfflineTestRuntime) over its synthetic bundle, behind the export's
// createSpecialistOrchestrator; its authorizedGenerate returns each corpus item's recorded answer (or a fault case's
// mutated answer), so no model is called.
//
// Invariants:
// - it runs only on a directory that carries UNREVIEWED-SIMULATION-COPY.txt (an export, never a checkout or a branch),
//   and on a copy of the agents repository; it never writes into either;
// - every fetch that is not to a loopback host is refused before it is sent (no provider, no network), and counted;
// - the turns it cannot run say so in its records; it never fabricates a turn, a verdict or a result: every answer it
//   records is the website's own response to a request it sent, and every verdict is the one the service answered
//   (a tampering case changes a verdict on its way back, and records that it did);
// - without the verified backend or the runtime copy it exits 3 and names what is missing, and run_sim.py reports the
//   website-path gates NOT RUN with that reason, never PASS.
//
// Usage: node website-driver.mjs --website <export> --agents <agents copy> --service <http://127.0.0.1:port>
//        --token-file <file> --users <users.json> --corpus <service corpus copy> --round <round> --out <dir>
//        [--faults <faults.json>] [--vectors <kit>/integration/vectors]
//
// Writes <out>/website-driver.json (schema epinoic.integration.sim-website-records.v1).
import { createHash, randomUUID } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const argv = process.argv.slice(2);
const args = {};
for (let i = 0; i < argv.length; i += 1) if (argv[i].startsWith("--")) args[argv[i].slice(2)] = argv[i + 1];

const WEBSITE_FILES = ["src/index.js", "src/verify/with-verification.js", "src/verify/release-gate.js", "src/verify/specialist-orchestrator.js",
  "src/chat/contract.js", "public/chat-contract.js", "tests/helpers/d1.js"];
const AGENTS_FILES = ["specialist-runtime/src/index.js", "specialist-runtime/fixtures/synthetic/harness.js",
  "specialist-runtime/fixtures/synthetic/gate-config.js", "specialist-runtime/fixtures/synthetic/manifest.js",
  "specialist-runtime/fixtures/synthetic/synthetic-bundle.txt"];
const missing = [];
if (!args.website || !existsSync(join(args.website, "UNREVIEWED-SIMULATION-COPY.txt"))) missing.push("a disposable website export (UNREVIEWED-SIMULATION-COPY.txt)");
for (const f of WEBSITE_FILES) if (!args.website || !existsSync(join(args.website, f))) missing.push(f);
for (const f of AGENTS_FILES) if (!args.agents || !existsSync(join(args.agents, f))) missing.push(`agents copy: ${f}`);
for (const k of ["service", "token-file", "users", "corpus", "round", "out"]) if (!args[k]) missing.push(`--${k}`);
if (missing.length > 0) {
  console.error(`not runnable: missing ${missing.join(", ")}${missing.some((m) => m.startsWith("src/verify")) ? " (patch set M not applied)" : ""}`);
  process.exit(3);
}

// Loopback only: replace fetch before anything of the export is imported.
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

const WEBSITE = resolve(args.website);
const AGENTS = resolve(args.agents);
const web = (p) => import(pathToFileURL(join(WEBSITE, p)).href);
const agentsModule = (p) => import(pathToFileURL(join(AGENTS, p)).href);

const { handleRequest } = await web("src/index.js");
const { errorResult, statusForError } = await web("src/chat/contract.js");
const { createSpecialistOrchestrator } = await web("src/verify/specialist-orchestrator.js");
const { countClaims } = await web("src/verify/decision-table.js");
const { createD1 } = await web("tests/helpers/d1.js");
const page = await web("public/chat-contract.js");
const runtimePackage = await agentsModule("specialist-runtime/src/index.js");
const harness = await agentsModule("specialist-runtime/fixtures/synthetic/harness.js");
const gates = await agentsModule("specialist-runtime/fixtures/synthetic/gate-config.js");
const manifests = await agentsModule("specialist-runtime/fixtures/synthetic/manifest.js");

const SERVICE = new URL(args.service);
if (!LOOPBACK.has(SERVICE.hostname)) {
  console.error("not runnable: the checks service must be on a loopback host");
  process.exit(3);
}
const TOKEN = readFileSync(args["token-file"], "utf8").trim();
const USERS = JSON.parse(readFileSync(args.users, "utf8"));
const ROUND = args.round;
const ROUND_DIR = join(args.corpus, ROUND);
const FAULTS = args.faults ? JSON.parse(readFileSync(args.faults, "utf8")) : [];
const VECTORS = args.vectors ?? null;
const OUT = args.out;
const sha256 = (text) => createHash("sha256").update(text, "utf8").digest("hex");

function corpusItem(name) {
  const p = join(ROUND_DIR, "specialists", `${name}.json`);
  if (!existsSync(p)) return null;
  return JSON.parse(readFileSync(p, "utf8"));
}

// ------------------------------------------------------------------------------------------------- the specialist runtime

// The agents repository's synthetic manifest and gate configuration, unchanged for History; the simulation's synthetic
// English specialist (subject map, environment sim) is the same entry under its slug, with the History synthetic gate
// configuration under its slug and the sources line optional (its corpus answer carries none). No runtime code changes.
const BUNDLE_BYTES = readFileSync(join(AGENTS, "specialist-runtime/fixtures/synthetic/synthetic-bundle.txt"));
const SIM_SLUGS = ["history", "english-a-literature"];
function simManifest() {
  const m = JSON.parse(JSON.stringify(manifests.SYNTHETIC_MANIFEST));
  const history = m.entries.find((e) => e.slug === "history");
  m.entries.push({ ...history, slug: "english-a-literature", displayName: "English A: Literature (SYNTHETIC simulation fixture)" });
  return m;
}
function gateFor(slug) {
  const g = JSON.parse(JSON.stringify(gates.SYNTHETIC_GATE_CONFIG));
  if (slug === "history") return g;
  return { ...g, slug, checks: { ...g.checks, "sources-line": { ...g.checks["sources-line"], required: false } } };
}
const runtime = runtimePackage.createOfflineTestRuntime({ manifest: simManifest(), gateConfigs: Object.fromEntries(SIM_SLUGS.map((s) => [s, gateFor(s)])) });
const bundles = new Map();
for (const slug of SIM_SLUGS) {
  bundles.set(slug, await runtime.loadPinnedBundle({ slug, bundleModule: harness.moduleForBytes(BUNDLE_BYTES, { slug }), environment: "offline-test" }));
}

// ------------------------------------------------------------------------------------------------- one user's world

const LOCAL = "http://127.0.0.1:8787";
const MAX_RESULT_BYTES = 65536;
const MAX_STATEMENTS = 36;

/** A fresh website world for one simulated user: its own D1, logs, counters and the transport to the service. */
function newWorld(user) {
  const db = createD1();
  db.applyMigrations();
  const env = { APP_ENV: "development", CHAT_BACKEND: "verified", CHAT_STATE: "d1", ROUTER_MODE: "mock", TRANSLATOR_MODE: "http",
    TRANSLATOR_BASE_URL: SERVICE.origin, TRANSLATOR_SERVICE_TOKEN: TOKEN, KIT_SIMULATION: "1", CHAT_DB: db };
  const w = { user, db, env, logs: [], counts: { capabilities: 0, check: 0, specialist: 0 }, mode: { kind: "normal" }, nowOffset: 0,
    verdicts: [], checkRequests: [], answers: new Map(), hooks: new Map(), tampered: [] };

  // The Worker's transport to the checks service: loopback, the bearer token as the client sets it, and the per-turn
  // behaviour of the simulated service (stopped, slower than the budget, a handshake mismatch, a tampered verdict).
  w.fetchImpl = async (input, init = {}) => {
    const url = urlOf(input);
    if (!LOOPBACK.has(url.hostname)) {
      fetchLog.refused.push(url.hostname);
      throw new Error(`the simulation refuses non-loopback host ${url.hostname}`);
    }
    const target = new URL(url.pathname + url.search, SERVICE.origin);
    if (url.pathname === "/v1/capabilities") {
      w.counts.capabilities += 1;
      if (w.mode.kind === "stopped") throw new TypeError("fetch failed (SYNTHETIC: the service is stopped)");
      const r = await globalThis.fetch(target, init);
      if (w.mode.kind !== "mismatch") return r;
      const caps = await r.json();
      caps.versions = { ...caps.versions, engine: "0.0.0-sim-mismatch" };
      return Response.json(caps, { status: r.status });
    }
    w.counts.check += 1;
    let body = null;
    try {
      body = JSON.parse(typeof init.body === "string" ? init.body : "null");
    } catch {
      body = null;
    }
    if (body) w.checkRequests.push(body);
    if (w.mode.kind === "stopped") throw new TypeError("fetch failed (SYNTHETIC: the service is stopped)");
    if (w.mode.kind === "slow") {
      // A service slower than the budget: no answer before the client's own timeout aborts the request.
      await new Promise((resolveSlow, rejectSlow) => {
        if (init.signal?.aborted) return rejectSlow(init.signal.reason ?? new Error("aborted"));
        init.signal?.addEventListener("abort", () => rejectSlow(init.signal.reason ?? new Error("aborted")), { once: true });
        setTimeout(resolveSlow, 600_000).unref?.();
      });
    }
    const r = await globalThis.fetch(target, init);
    const text = await r.text();
    let verdict = null;
    try {
      verdict = JSON.parse(text);
    } catch {
      verdict = null;
    }
    if (verdict && r.status === 200) w.verdicts.push({ requestId: body?.ids?.request_id ?? null, verdict: structuredClone(verdict) });
    if (w.mode.kind === "tamper" && verdict && r.status === 200) {
      const changed = tamper(w.mode.case, verdict);
      w.tampered.push({ case: w.mode.case, requestId: body?.ids?.request_id ?? null });
      return new Response(JSON.stringify(changed), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return new Response(text, { status: r.status, headers: { "Content-Type": r.headers.get("Content-Type") ?? "application/json" } });
  };

  // The specialist: the agents runtime, counted; its authorizedGenerate returns the turn's recorded (or mutated) answer.
  const counted = {
    getCapabilities: (a) => {
      const caps = runtime.getCapabilities(a);
      if (w.mode.kind !== "subject_unavailable") return caps;
      return { ...caps, entries: caps.entries.map((e) => ({ ...e, available: false })) };
    },
    runSpecialistTurn: (input) => {
      w.counts.specialist += 1;
      return runtime.runSpecialistTurn(input);
    },
  };
  const inner = createSpecialistOrchestrator({
    runtime: counted,
    redactForLog: runtimePackage.redactForLog,
    bundleFor: async (slug) => bundles.get(slug),
    turnInputFor: ({ slug, bundle, request, context }) => ({
      slug, mode: "pilot-single-turn-no-tools", environment: "offline-test", bundle, message: request.message, priorTurns: [],
      limits: harness.SYNTHETIC_LIMITS,
      turn: { conversationId: request.conversationId, turnId: context.turn.turnId, turnVersion: request.expectedTurnVersion + 1, attemptId: context.turn.attemptId },
      signal: context.signal,
      authorizedGenerate: async () => {
        const hook = w.hooks.get(request.clientTurnId);
        if (hook) await hook();
        const text = w.answers.get(request.clientTurnId);
        if (typeof text !== "string") return { status: "failed", error: { code: "sim_no_answer" }, usage: null, providerEvidence: null };
        return { status: "completed", output: { text, finishReason: "stop" }, usage: null, providerEvidence: null };
      },
    }),
    failure: (rid, code) => ({ status: statusForError(code), result: errorResult(rid, code) }),
  });
  w.chatOptions = { verified: { inner }, log: (entry) => w.logs.push(entry), ctx: { waitUntil: () => {} }, now: () => Date.now() + w.nowOffset };

  w.post = async (body) => {
    const before = db.log.length;
    const request = new Request(`${LOCAL}/api/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const response = await handleRequest(request, env, w.fetchImpl, w.chatOptions);
    const text = await response.text();
    let parsed = null;
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = null;
    }
    return { status: response.status, body: parsed, bytes: Buffer.byteLength(text, "utf8"), statements: db.log.length - before,
      headers: { backend: response.headers.get("X-Chat-Backend"), simulated: response.headers.get("X-Chat-Simulated"), replay: response.headers.get("X-Chat-Replay") } };
  };
  w.cancel = async (clientTurnId) => {
    const before = db.log.length;
    const request = new Request(`${LOCAL}/api/chat/cancel`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ clientTurnId }) });
    const response = await handleRequest(request, env, w.fetchImpl, w.chatOptions);
    return { status: response.status, body: await response.json(), statements: db.log.length - before };
  };
  w.conversation = async (id) => {
    const response = await handleRequest(new Request(`${LOCAL}/api/conversations/${id}`), env, w.fetchImpl, w.chatOptions);
    return response.json();
  };
  w.turnRow = (clientTurnId) => db.raw.prepare("SELECT conversation_id, state, attempt_id, error_code, simulated, result_json FROM turns WHERE client_turn_id = ?").get(clientTurnId) ?? null;
  return w;
}

// ------------------------------------------------------------------------------------------------- tampering (W-T1..W-T8)

const TAMPER_CASES = ["W-T1-tampered-decision", "W-T2-substituted-answer", "W-T3-verdict-of-another-attempt", "W-T4-changed-scope-statement",
  "W-T5-extra-field", "W-T6-forged-clearance-state", "W-T7-status-shown-as-success", "W-T8-stripped-signature"];
function expectedRawCode(name) {
  if (!VECTORS) return null;
  const p = join(VECTORS, "verdict-binding", `${name}.json`);
  return existsSync(p) ? JSON.parse(readFileSync(p, "utf8")).expect.raw_code : null;
}
function vectorField(name, path) {
  const v = JSON.parse(readFileSync(join(VECTORS, "verdict-binding", `${name}.json`), "utf8")).verdict;
  return path.reduce((o, k) => (o === undefined || o === null ? undefined : o[k]), v);
}

/** The service's real verdict for this turn, changed as the case's vector changes the bound deliver vector. */
function tamper(name, verdict) {
  const v = structuredClone(verdict);
  switch (name.slice(0, name.indexOf("-", 2))) {
    case "W-T1": { // the decision says deliver while a material claim is refuted
      const first = (v.claims ?? [])[0];
      v.claims = [{ ...(first ?? { claim_id: "c1", materiality: "material", role: "point", excerpt: "x", source: "translation", attempt: "attempted",
        fidelity: "missing", evidence_resolved: false, release_permitted: false, result_id: null, binding_digest: null }), materiality: "material", formal: "COUNTEREXAMPLE" }];
      v.counts = countClaims(v.claims);
      return v;
    }
    case "W-T2": { // the verdict binds another answer than the one the Worker holds
      const other = sha256("SYNTHETIC substituted answer: not the specialist's text.");
      if (v.delivery?.deliverable) v.delivery.deliverable.answer_sha256 = other;
      for (const a of v.bound?.answers ?? []) a.answer_sha256 = other;
      return v;
    }
    case "W-T3": // a verdict of another attempt
      v.ids.request_id = `a_${"0".repeat(30)}99`;
      return v;
    case "W-T4":
      v.scope_statement = vectorField(name, ["scope_statement"]);
      return v;
    case "W-T5":
      v.verified = vectorField(name, ["verified"]);
      return v;
    case "W-T6":
      v.overseer.state = vectorField(name, ["overseer", "state"]);
      return v;
    case "W-T7":
      if (Array.isArray(v.claims) && v.claims.length > 0) v.claims[0].formal = vectorField(name, ["claims", 0, "formal"]);
      else v.claims = [{ claim_id: "c1", materiality: "material", role: "point", excerpt: "x", source: "translation", formal: vectorField(name, ["claims", 0, "formal"]),
        attempt: "attempted", fidelity: "missing", evidence_resolved: false, release_permitted: false, result_id: null, binding_digest: null }];
      return v;
    case "W-T8":
      delete v.signature;
      return v;
    default:
      throw new Error(`unknown tampering case ${name}`);
  }
}

// ------------------------------------------------------------------------------------------------- the replay

const records = { schema: "epinoic.integration.sim-website-records.v1", status: "ran", round: ROUND,
  website: readFileSync(join(WEBSITE, "UNREVIEWED-SIMULATION-COPY.txt"), "utf8").trim().split("\n")[0],
  agents_commit: existsSync(join(AGENTS, ".kit-archive-commit")) ? readFileSync(join(AGENTS, ".kit-archive-commit"), "utf8").trim() : null,
  turns: [], tamper: {}, faults: [], displays: [], verdicts: [], invariants: {}, fetch: fetchLog, not_run: [] };

let seq = 0;
const newId = (prefix) => `${prefix}_${String((seq += 1)).padStart(6, "0")}_${randomUUID().replaceAll("-", "").slice(0, 12)}`;
const MIXED = "SYNTHETIC: How does the poem's final image comment on the Treaty of Versailles?";

function display(r) {
  const b = r.body ?? {};
  if (b.kind !== "answer") return null;
  const checks = Array.isArray(b.checks) ? b.checks : [];
  const simulated = r.headers.simulated === "1";
  return { review: b.review, summary: b.checksSummary, badge: page.checksBadge(b.checksSummary, simulated ? " (simulated)" : "")[0],
    labels: checks.map((c) => ({ formal: c.formal, text: page.checkLabel(c) })), scope_statement_shown: Array.isArray(b.checks), simulated };
}

function record(w, t, r, extra = {}) {
  const b = r.body ?? {};
  const row = t.clientTurnId ? w.turnRow(t.clientTurnId) : null;
  const rec = { user: w.user, turn: t.index, item: t.item, action: t.action, clientTurnId: t.clientTurnId ?? null, status: r.status,
    kind: b.kind ?? null, code: b.code ?? null, retryable: b.retryable ?? null, review: b.review ?? null, checksSummary: b.checksSummary ?? null,
    checks: Array.isArray(b.checks) ? b.checks : null, text_sha256: typeof b.text === "string" ? sha256(b.text) : null,
    headers: r.headers, bytes: r.bytes, statements: r.statements, calls: { ...w.counts },
    stored: row === null ? null : { state: row.state, attempt_id: row.attempt_id, error_code: row.error_code, simulated: row.simulated },
    ...extra };
  records.turns.push(rec);
  const d = display(r);
  if (d) records.displays.push(d);
  return rec;
}

const delta = (w, before) => ({ capabilities: w.counts.capabilities - before.capabilities, check: w.counts.check - before.check, specialist: w.counts.specialist - before.specialist });

async function runWebsiteUser(u) {
  const w = newWorld(u.user);
  let conversationId = null;
  let last = null; // { body, clientTurnId }
  const turns = u.turns.map((t, index) => ({ ...t, index }));
  for (let k = 0; k < turns.length; k += 1) {
    const t = turns[k];
    const item = corpusItem(t.item);
    if (item === null) {
      records.not_run.push({ user: u.user, turn: t.index, reason: `no corpus item ${t.item}` });
      continue;
    }
    w.mode = { kind: "normal" };
    w.nowOffset = 0;
    const before = { ...w.counts };
    const fresh = () => {
      const id = newId("turn");
      w.answers.set(id, item.response_text);
      const body = { message: item.question, clientTurnId: id };
      if (conversationId !== null && t.action !== "send") return { ...body, conversationId };
      return body;
    };
    const withVersion = async (body) => {
      if (!body.conversationId) return body;
      const c = await w.conversation(body.conversationId);
      return { ...body, expectedTurnVersion: c?.conversation?.turnVersion ?? 0 };
    };
    if (t.action === "send" || t.action === "follow_up") {
      if (t.action === "send") conversationId = null;
      const body = await withVersion(fresh());
      t.clientTurnId = body.clientTurnId;
      const r = await w.post(body);
      record(w, t, r, { delta: delta(w, before) });
      conversationId = r.body?.conversationId ?? w.turnRow(body.clientTurnId)?.conversation_id ?? conversationId;
      last = { body, clientTurnId: body.clientTurnId, response: r };
    } else if (t.action === "retry") {
      if (last === null) {
        records.not_run.push({ user: u.user, turn: t.index, reason: "a retry without an earlier turn" });
        continue;
      }
      t.clientTurnId = last.clientTurnId;
      const r = await w.post(last.body);
      const same = JSON.stringify({ ...r.body, requestId: null }) === JSON.stringify({ ...last.response.body, requestId: null });
      record(w, t, r, { delta: delta(w, before), replay_of: last.clientTurnId, same_as_first: same, first_status: last.response.status });
    } else if (t.action === "cancel") {
      const body = fresh();
      t.clientTurnId = body.clientTurnId;
      let cancelled = null;
      w.hooks.set(body.clientTurnId, async () => {
        cancelled = await w.cancel(body.clientTurnId); // during the specialist's generation: before the checks call
      });
      const r = await w.post(body);
      if (cancelled !== null) r.statements -= cancelled.statements; // the cancel request ran inside this one
      record(w, t, r, { delta: delta(w, before), cancel: cancelled });
    } else if (t.action === "concurrent") {
      // Two sends into one conversation: the second is posted while the first is still being answered.
      const second = turns[k + 1];
      const secondItem = second && second.action === "concurrent" ? corpusItem(second.item) : null;
      const body = fresh();
      t.clientTurnId = body.clientTurnId;
      let secondResponse = null;
      let secondBody = null;
      if (secondItem !== null) {
        w.hooks.set(body.clientTurnId, async () => {
          const conv = w.turnRow(body.clientTurnId)?.conversation_id ?? null;
          const id = newId("turn");
          w.answers.set(id, secondItem.response_text);
          secondBody = { message: secondItem.question, clientTurnId: id, ...(conv ? { conversationId: conv, expectedTurnVersion: 0 } : {}) };
          secondResponse = await w.post(secondBody);
        });
      }
      const r = await w.post(body);
      // the second send ran inside the first one's request: its statements are its own, not the first's
      if (secondResponse !== null) r.statements -= secondResponse.statements;
      record(w, t, r, { delta: delta(w, before) });
      if (secondResponse !== null) {
        record(w, { ...second, index: second.index, clientTurnId: secondBody.clientTurnId }, secondResponse, { concurrent_with: body.clientTurnId });
        k += 1;
      }
      conversationId = r.body?.conversationId ?? conversationId;
      last = { body, clientTurnId: body.clientTurnId, response: r };
    } else if (t.action === "service_stopped") {
      const body = fresh();
      t.clientTurnId = body.clientTurnId;
      w.mode = { kind: "stopped" };
      const r = await w.post(body);
      record(w, t, r, { delta: delta(w, before) });
      w.mode = { kind: "normal" };
      const again = { ...w.counts };
      const r2 = await w.post(body); // the service is back: the retry re-arms the turn
      record(w, { ...t, action: "service_stopped:retry" }, r2, { delta: delta(w, again), replay_of: body.clientTurnId });
      last = { body, clientTurnId: body.clientTurnId, response: r2 };
    } else if (t.action === "service_slow") {
      const body = fresh();
      t.clientTurnId = body.clientTurnId;
      w.mode = { kind: "slow" };
      // A fake clock (the verified backend's injectable now) leaves just over checks_min_ms of the turn's deadline, so the
      // client's own timeout (the budget plus the checks tail) fires in about 18 s instead of 80 s; the service never answers.
      w.nowOffset = 180_000 - 15_000 - 2_000 - 3_000 - 500;
      const r = await w.post(body);
      record(w, t, r, { delta: delta(w, before) });
    } else if (t.action === "clock_past_cache") {
      const body = await withVersion(fresh());
      t.clientTurnId = body.clientTurnId;
      w.nowOffset = 61_000; // past the 60 s handshake cache age
      const r = await w.post(body);
      record(w, t, r, { delta: delta(w, before) });
      last = { body, clientTurnId: body.clientTurnId, response: r };
    } else if (t.action === "handshake_mismatch") {
      const body = fresh();
      t.clientTurnId = body.clientTurnId;
      w.mode = { kind: "mismatch" };
      const r = await w.post(body);
      record(w, t, r, { delta: delta(w, before) });
    } else if (t.action === "subject_unavailable") {
      const body = fresh();
      t.clientTurnId = body.clientTurnId;
      w.mode = { kind: "subject_unavailable" };
      const r = await w.post(body);
      record(w, t, r, { delta: delta(w, before) });
    } else if (t.action === "mixed_subject") {
      const id = newId("turn");
      w.answers.set(id, item.response_text);
      const body = { message: MIXED, clientTurnId: id };
      t.clientTurnId = id;
      const r = await w.post(body);
      record(w, t, r, { delta: delta(w, before) });
    } else if (t.action === "tamper") {
      if (!VECTORS) {
        records.not_run.push({ user: u.user, turn: t.index, reason: "no --vectors: the tampering cases have no expected codes" });
        continue;
      }
      for (const name of TAMPER_CASES) {
        const id = newId("turn");
        w.answers.set(id, item.response_text);
        const body = { message: item.question, clientTurnId: id };
        w.mode = { kind: "tamper", case: name };
        const b0 = { ...w.counts };
        const r = await w.post(body);
        const rec = record(w, { ...t, action: `tamper:${name}`, clientTurnId: id }, r, { delta: delta(w, b0) });
        const key = name.slice(0, name.indexOf("-", 2));
        records.tamper[key] = { expected: expectedRawCode(name), got: rec.stored?.error_code ?? null, status: r.status, code: rec.code,
          stored_answer: rec.stored?.state === "completed" };
      }
    } else {
      records.not_run.push({ user: u.user, turn: t.index, reason: `action ${t.action} is not a website-path action` });
    }
  }
  return w;
}

async function runFaults() {
  // Each fault case: its own conversation, the item's question, the mutated answer from the specialist.
  const w = newWorld("sim-faults");
  for (const f of FAULTS) {
    const item = corpusItem(f.item);
    if (item === null || !["History", "English A: Literature"].includes(item.subject)) continue; // STEM cases go through the agents path
    const id = newId("turn");
    w.answers.set(id, f.text);
    const before = { ...w.counts };
    const r = await w.post({ message: item.question, clientTurnId: id });
    const rec = record(w, { item: f.item, action: `fault:${f.kind}`, index: 0, clientTurnId: id }, r, { delta: delta(w, before), fault_case: f.case });
    const verdict = w.verdicts.find((v) => v.requestId === rec.stored?.attempt_id)?.verdict ?? null;
    records.faults.push({ case: f.case, item: f.item, kind: f.kind, status: r.status, code: rec.code, raw_code: rec.stored?.error_code ?? null,
      website_refused: r.status === 422 || r.status === 502, website_codes: verdict?.receipt?.error_codes ?? [], receipt_status: verdict?.receipt?.status ?? null,
      website_labelled_checked: rec.checksSummary === "formally_checked", answer_sha256: sha256(f.text) });
  }
  return w;
}

const worlds = [];
for (const u of USERS.users.filter((x) => x.path === "website")) worlds.push(await runWebsiteUser(u));
if (FAULTS.length > 0) worlds.push(await runFaults());

// ------------------------------------------------------------------------------------------------- the invariants (G-INV)

const verdictsByAttempt = new Map();
for (const w of worlds) for (const v of w.verdicts) verdictsByAttempt.set(v.requestId, v.verdict);
records.verdicts = [...verdictsByAttempt.values()];
const answered = records.turns.filter((t) => t.stored?.state === "completed" && t.kind === "answer");
const inv = {};
// No answer is stored without a deliver verdict for its own attempt.
inv.no_answer_without_deliver = answered.length === 0 ? null : answered.every((t) => {
  if (String(t.action).startsWith("tamper:")) return false;
  const v = verdictsByAttempt.get(t.stored.attempt_id);
  return v?.delivery?.decision === "deliver" && v?.delivery?.deliverable?.answer_sha256 === t.text_sha256;
});
// Replays are unchanged and make no service or specialist call.
const replays = records.turns.filter((t) => t.action === "retry" && t.first_status === 200);
inv.replays_unchanged_without_calls = replays.length === 0 ? null : replays.every((t) => t.headers.replay === "1" && t.same_as_first === true
  && t.delta.check === 0 && t.delta.specialist === 0 && t.delta.capabilities === 0);
// Cancels fence: a turn stopped during the specialist's generation makes no checks call and stores no answer.
const cancels = records.turns.filter((t) => t.action === "cancel");
inv.cancels_fence = cancels.length === 0 ? null : cancels.every((t) => t.code === "turn_cancelled" && t.delta.check === 0 && t.stored?.state !== "completed");
// One pending submission per conversation.
const seconds = records.turns.filter((t) => t.concurrent_with);
inv.one_pending_submission = seconds.length === 0 ? null : seconds.every((t) => t.status === 409 && t.code === "turn_conflict");
// Every result at most 64 KiB; every request at most 36 statements.
inv.results_at_most_64_kib = records.turns.length === 0 ? null : records.turns.every((t) => t.bytes <= MAX_RESULT_BYTES);
inv.statements_at_most_36 = records.turns.length === 0 ? null : records.turns.every((t) => t.statements <= MAX_STATEMENTS);
// Logs carry labels only: no question, answer or excerpt text in any log line.
const texts = new Set();
for (const w of worlds) for (const text of w.answers.values()) texts.add(text);
for (const u of USERS.users) for (const t of u.turns) { const it = corpusItem(t.item); if (it) texts.add(it.question); }
const excerpts = new Set(records.verdicts.flatMap((v) => (v.claims ?? []).map((c) => c.excerpt)));
const logText = worlds.flatMap((w) => w.logs.map((l) => JSON.stringify(l))).join("\n");
inv.logs_labels_only = logText.length === 0 ? null : [...texts, ...excerpts].every((t) => t.length < 12 || !logText.includes(t.slice(0, 60)));
// Only loopback hosts are fetched.
inv.loopback_only = fetchLog.loopback === 0 ? null : fetchLog.refused.length === 0;
// No specialist call, nothing paid, before a compatible handshake or for an unavailable or mixed subject.
const unpaid = records.turns.filter((t) => ["handshake_mismatch", "subject_unavailable", "mixed_subject", "service_stopped"].includes(t.action));
inv.no_specialist_call_before_readiness = unpaid.length === 0 ? null : unpaid.every((t) => t.delta.specialist === 0 && t.delta.check === 0);
records.invariants = inv;

mkdirSync(OUT, { recursive: true });
writeFileSync(join(OUT, "website-driver.json"), JSON.stringify(records, null, 1));
console.log(`website driver: ${records.turns.length} turn(s), ${Object.keys(records.tamper).length} tampering case(s), ${records.faults.length} fault case(s), `
  + `${records.not_run.length} not run; refused hosts: ${fetchLog.refused.length}`);
process.exit(0);
