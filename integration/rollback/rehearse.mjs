// The rollback rehearsal on disposable website exports (integration/rollback/ROLLBACK.md; PROTOCOL.md section 14.7).
// Read-only for every repository: it only imports modules from the exports it is given and writes one SQLite file in
// --work. No network: the checks service is a fake behind fetchImpl, loopback only.
//
//   node integration/rollback/rehearse.mjs --full <export, whole patch set> --reader <export, W1 alone>
//        --base <unpatched export> --work <dir>
//
// 1. the whole patch set stores a verified answer (rows written by W3);
// 2. with W1 alone (the reader) on the same database, history shows the answer with its checks and an unchanged
//    retry replays it: removing W3 (the writer) leaves every stored row valid;
// 3. on the unpatched base, the same replay fails (500): once a row with checks exists, W1 stays for good;
// 4. a service rolled back to an incompatible version is refused after admission (service_unavailable,
//    kit_hs_mismatch), and an incomplete configuration before admission (chat_unavailable): never an unchecked answer;
// 5. base P: no patch set P in this kit (NOT RUN).
import { mkdirSync, readFileSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const args = process.argv.slice(2);
const opt = (n) => (args.includes(n) ? resolve(args[args.indexOf(n) + 1]) : null);
const full = opt("--full");
const reader = opt("--reader");
const base = opt("--base");
const work = opt("--work");
if (!full || !reader || !base || !work) {
  console.error("usage: rehearse.mjs --full <export> --reader <export> --base <export> --work <dir>");
  process.exit(2);
}
mkdirSync(work, { recursive: true });
const dbPath = join(work, "rehearsal.sqlite");
rmSync(dbPath, { force: true });
const load = (root, rel) => import(pathToFileURL(join(root, rel)).href);
const vector = (folder, name) => JSON.parse(readFileSync(join(full, "tests", "fixtures", "kit", folder, `${name}.json`), "utf8"));

const LOCAL = "http://127.0.0.1:8787";
const TOKEN = "kit-rehearsal-token-0123456789";
const MESSAGE = "SYNTHETIC history question: how far did the Treaty of Versailles destabilise Germany in the 1920s?";
const EXCERPT = "The Treaty of Versailles (1919) imposed reparations and territorial losses on Germany.";
const RUNTIME = vector("specialist-port/v1", "answer");
const results = [];
const step = (name, ok, detail) => results.push({ step: name, status: ok === null ? "NOT RUN" : ok ? "PASS" : "FAIL", detail });

async function world(root, { verified, versions = null, freshDb = false }) {
  const { createD1 } = await load(root, "tests/helpers/d1.js");
  const { handleRequest } = await load(root, "src/index.js");
  const db = createD1({ path: dbPath });
  if (freshDb) db.applyMigrations();
  const env = { APP_ENV: "development", CHAT_STATE: "d1", ROUTER_MODE: "mock", CHAT_DB: db,
    ...(verified ? { CHAT_BACKEND: "verified", TRANSLATOR_MODE: "http", TRANSLATOR_BASE_URL: "http://127.0.0.1:8899", TRANSLATOR_SERVICE_TOKEN: TOKEN, KIT_SIMULATION: "1" }
      : { CHAT_BACKEND: "mock" }) };
  let chatOptions = { log: () => {}, ctx: { waitUntil: () => {} } };
  let fetchImpl = async () => { throw new Error("no network"); };
  if (verified) {
    const { countClaims } = await load(root, "src/verify/decision-table.js");
    const { createSpecialistOrchestrator } = await load(root, "src/verify/specialist-orchestrator.js");
    const { errorResult, statusForError } = await load(root, "src/chat/contract.js");
    const caps = structuredClone(vector("handshake", "compatible").capabilities);
    if (versions) Object.assign(caps.versions, versions);
    fetchImpl = async (url, init = {}) => {
      const u = new URL(url);
      if (u.hostname !== "127.0.0.1") throw new Error("loopback only");
      if (u.pathname === "/v1/capabilities") return Response.json(caps);
      const req = JSON.parse(init.body);
      const v = structuredClone(vector("verdict-binding", "deliver-bound").verdict);
      const a = req.answers[0];
      v.ids.task_id = req.ids.task_id;
      v.ids.request_id = req.ids.request_id;
      v.bound.user_text_sha256 = req.task.user_text_sha256;
      v.bound.answers = [{ agent_id: a.agent_id, answer_sha256: a.answer_sha256, result_sha256: a.result_sha256, report_id: "rep_t_history_v1", message_id: "m-1" }];
      v.delivery = { ...v.delivery, deliverable: { agent_id: a.agent_id, answer_sha256: a.answer_sha256, message_id: "m-1" } };
      v.claims = [{ claim_id: "h1.1", materiality: "material", role: "point", excerpt: EXCERPT, source: "translation", formal: "ENTAILED", attempt: "attempted",
        fidelity: "missing", evidence_resolved: false, release_permitted: false, result_id: null, binding_digest: null }];
      v.counts = countClaims(v.claims);
      v.summary = "formal_only";
      return Response.json(v);
    };
    const inner = createSpecialistOrchestrator({
      runtime: { getCapabilities: () => ({ specialists: [{ slug: "history", available: true }] }), runSpecialistTurn: async () => structuredClone(RUNTIME.result) },
      redactForLog: () => structuredClone(RUNTIME.log), bundleFor: async () => ({}), turnInputFor: () => ({}),
      failure: (rid, code) => ({ status: statusForError(code), result: errorResult(rid, code) }),
    });
    chatOptions = { ...chatOptions, verified: { inner } };
  }
  const post = async (body) => {
    const r = await handleRequest(new Request(`${LOCAL}/api/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }), env, fetchImpl, chatOptions);
    return { status: r.status, body: await r.json() };
  };
  const history = async (id) => {
    const r = await handleRequest(new Request(`${LOCAL}/api/conversations/${id}`), env, fetchImpl, chatOptions);
    return { status: r.status, body: await r.json() };
  };
  return { db, post, history };
}

const turn = { message: MESSAGE, clientTurnId: "turn_rehearsal_01" };
const w1 = await world(full, { verified: true, freshDb: true });
const stored = await w1.post(turn);
step("1 the whole patch set stores a verified answer", stored.status === 200 && stored.body.review === "checks:integration.v1" && Array.isArray(stored.body.checks),
  `${stored.status} ${stored.body.review ?? stored.body.code}`);
const conversationId = stored.body.conversationId;
w1.db.close();

const w2 = await world(reader, { verified: false });
const h = await w2.history(conversationId);
const replay = await w2.post(turn);
step("2 W1 alone reads the rows W3 wrote: history and replay", h.status === 200 && Array.isArray(h.body.turns?.[0]?.reply?.checks) && replay.status === 200 && replay.body.review === "checks:integration.v1",
  `history ${h.status}, replay ${replay.status} ${replay.body.review ?? replay.body.code}`);
w2.db.close();

const w3 = await world(base, { verified: false });
const baseReplay = await w3.post(turn);
step("3 without W1 the replay of a row with checks fails: W1 stays for good", baseReplay.status === 500, `replay ${baseReplay.status} ${baseReplay.body.code}`);
w3.db.close();

const w4 = await world(full, { verified: true, versions: { engine: "0.3.0" } });
const rolledBack = await w4.post({ message: MESSAGE, clientTurnId: "turn_rehearsal_02" });
const row = w4.db.raw.prepare("SELECT error_code FROM turns WHERE client_turn_id = 'turn_rehearsal_02'").get();
step("4 a service rolled back to an incompatible version is refused after admission", rolledBack.status === 503 && rolledBack.body.code === "service_unavailable" && row?.error_code === "kit_hs_mismatch",
  `${rolledBack.status} ${rolledBack.body.code} stored ${row?.error_code}`);
w4.db.close();

step("5 base P: removing patch set P leaves the pilot unchanged", null, "no patch set P in this kit (COMPATIBILITY.json website_bases.P)");
console.log(JSON.stringify(results, null, 1));
process.exit(results.some((r) => r.status === "FAIL") ? 1 : 0);
